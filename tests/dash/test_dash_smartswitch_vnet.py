"""
Module: tests.dash
File: test_dash_smartswitch_vnet.py
Description:
    DASH (Disaggregated API for SONiC Hosts) SmartSwitch VNET-to-VNET test suite.
    This test module validates outbound VNET traffic transformation on SmartSwitch topology,
    verifying the complete data path from VM to PE (Provider Edge) through DPU and NPU.

Test Intent:
    - Validate SmartSwitch outbound VNET traffic transformation
    - Verify packet encapsulation/decapsulation through DPU-NPU dataplane
    - Test VXLAN UDP source port range configuration on DPU
    - Ensure proper routing of packets from local VMs to remote endpoints
    - Validate inner packet types (UDP, TCP, ICMP echo request/reply)

Topology:
    - smartswitch: SmartSwitch topology with DPU-NPU architecture
    - Requires DPU-NPU dataplane interface IP assignments
    - Test traffic flows: VM -> DPU -> NPU -> PE

Fixtures Used:
    - localhost: Ansible localhost for configuration management
    - duthost: Device Under Test (NPU) host object
    - ptfhost: PTF (Packet Test Framework) host
    - ptfadapter: PTF adapter for packet injection/verification
    - dpuhosts: List of DPU host objects
    - dpu_index: Index of DPU to use for testing
    - dash_smartswitch_vnet_config: VNET configuration for SmartSwitch
    - skip_config: Flag to skip configuration application
    - skip_cleanup: Flag to skip cleanup after tests
    - skip_dataplane_checking: Flag to skip dataplane verification
    - inner_packet_type: Type of inner packet (udp/tcp/echo_request/echo_reply)
    - set_vxlan_udp_sport_range: Fixture to configure VXLAN UDP source port range
    - add_npu_static_routes_vnet: Fixture to add static routes on NPU
    - dpu_setup_vnet: Fixture to setup DPU for VNET testing
    - common_setup_teardown: Main setup/teardown fixture for test configuration

Dependencies:
    - constants: DASH test constants for interface/IP configuration
    - gnmi_utils: gNMI utilities for configuration application
    - dash_utils: DASH-specific utility functions
    - packets: Packet generation utilities
    - tests.common.config_reload: Configuration reload utilities

Notes:
    - Uses gNMI API for configuration by default (ENABLE_GNMI_API = True)
    - Requires 180-second sleep workaround for initial DASH object configuration
    - Related GitHub issue: https://github.com/sonic-net/sonic-swss-common/pull/1068
    - Config reload used for cleanup due to route rule removal bug
    - Related GitHub issue: https://github.com/sonic-net/sonic-buildimage/issues/23590
    - Test validates multiple inner packet types via parameterization
    - VXLAN UDP source port range is configurable per DPU type (Pensando workaround included)

Git History (last 3 commits):
    195f5706a [SmartSwitch] Restore dash smartswitch vnet after protobuf updates (#20998)
    2c20c10f5 [DASH] Need to avoid skipping the dash tests on smartswitch (#20958)
    48edf5b91 add smartswitch vnet2vnet DASH tests (#17042)
"""

import logging
import pytest
import ptf.testutils as testutils
import packets
import time
import json

from constants import LOCAL_PTF_INTF, REMOTE_PA_IP, REMOTE_PTF_RECV_INTF, REMOTE_DUT_INTF, \
    VXLAN_UDP_BASE_SRC_PORT, VXLAN_UDP_SRC_PORT_MASK
from gnmi_utils import apply_gnmi_file
from tests.common.dash_utils import render_template_to_host, apply_swssconfig_file
from tests.dash.conftest import get_interface_ip
from tests.common import config_reload

APPLIANCE_VIP = "10.1.0.5"
ENABLE_GNMI_API = True

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('smartswitch'),
    pytest.mark.disable_loganalyzer,
    pytest.mark.skip_check_dut_health
]


@pytest.fixture(scope="module", autouse=True)
def dpu_setup_vnet(duthost, dpuhosts, dpu_index, skip_config):
    if skip_config:

        return
    dpuhost = dpuhosts[dpu_index]
    # explicitly add mgmt IP route so the default route doesn't disrupt SSH access
    dpuhost.shell(f'ip route replace {duthost.mgmt_ip}/32 via 169.254.200.254')
    intfs = dpuhost.shell("show ip int")["stdout"]
    dpu_cmds = list()
    if "Loopback0" not in intfs:
        dpu_cmds.append("config loopback add Loopback0")
        dpu_cmds.append(f"config int ip add Loopback0 {APPLIANCE_VIP}/32")

    if dpuhost.npu_data_port_ip:
        dpu_cmds.append(f"ip route replace default via {dpuhost.npu_data_port_ip}")
    if len(dpu_cmds) > 0:
        dpuhost.shell_cmds(cmds=dpu_cmds)


@pytest.fixture(scope="module", autouse=True)
def add_npu_static_routes_vnet(duthost, dash_smartswitch_vnet_config, skip_config, skip_cleanup, dpu_index, dpuhosts):
    if not skip_config:
        dpuhost = dpuhosts[dpu_index]
        cmds = []
        pe_nexthop_ip = get_interface_ip(duthost, dash_smartswitch_vnet_config[REMOTE_DUT_INTF]).ip + 1
        cmds.append(f"ip route replace {dash_smartswitch_vnet_config[REMOTE_PA_IP]}/32 via {pe_nexthop_ip}")
        if dpuhost.dpu_data_port_ip:
            cmds.append(f"ip route replace {APPLIANCE_VIP}/32 via {dpuhost.dpu_data_port_ip}")
        logger.info(f"Adding static routes: {cmds}")
        duthost.shell_cmds(cmds=cmds)

    yield

    if not skip_config and not skip_cleanup:
        dpuhost = dpuhosts[dpu_index]
        cmds = []
        if dpuhost.dpu_data_port_ip:
            cmds.append(f"ip route del {dash_smartswitch_vnet_config[REMOTE_PA_IP]}/32 via {pe_nexthop_ip}")
        cmds.append(f"ip route del {APPLIANCE_VIP}/32 via {dpuhost.dpu_data_port_ip}")
        logger.info(f"Removing static routes: {cmds}")
        duthost.shell_cmds(cmds=cmds)


@pytest.fixture(scope="module", autouse=True)
def set_vxlan_udp_sport_range(dpuhosts, dpu_index):
    """
    Configure VXLAN UDP source port range in dpu configuration.
    """
    dpuhost = dpuhosts[dpu_index]
    vxlan_sport_config = [
        {
            "SWITCH_TABLE:switch": {
                "vxlan_sport": VXLAN_UDP_BASE_SRC_PORT,
                "vxlan_mask": VXLAN_UDP_SRC_PORT_MASK,
                "vxlan_security": "true"
            },
            "OP": "SET"
        }
    ]

    logger.info(f"Setting VXLAN source port config: {vxlan_sport_config}")
    config_path = "/tmp/vxlan_sport_config.json"
    dpuhost.copy(content=json.dumps(vxlan_sport_config, indent=4), dest=config_path, verbose=False)
    apply_swssconfig_file(dpuhost, config_path)
    if 'pensando' in dpuhost.facts['asic_type']:
        logger.warning("Applying Pensando DPU VXLAN sport workaround")
        dpuhost.shell("pdsctl debug update device --vxlan-port 4789 --vxlan-src-ports 5120-5247")
    yield
    if str(VXLAN_UDP_BASE_SRC_PORT) in dpuhost.shell("redis-cli -n 0 hget SWITCH_TABLE:switch vxlan_sport")['stdout']:
        config_reload(dpuhost, safe_reload=True, yang_validate=False)


@pytest.fixture(scope="module", autouse=True)
def common_setup_teardown(
        localhost,
        duthost,
        ptfhost,
        dpu_index,
        dash_smartswitch_vnet_config,
        skip_config,
        dpuhosts,
        add_npu_static_routes_vnet,
        dpu_setup_vnet,
        set_vxlan_udp_sport_range):
    if skip_config:
        return

    dpuhost = dpuhosts[dpu_index]
    host = f"dpu{dpuhost.dpu_index}"
    op = "SET"
    # Until this fix and related are in 202506 release this workaround is needed
    # Issue observed is that first set of DASH objects is not configured
    # https://github.com/sonic-net/sonic-swss-common/pull/1068
    time.sleep(180)
    for i in range(0, 4):
        config = f"dash_smartswitch_vnet_{i}"
        template_name = "{}.j2".format(config)
        dest_path = "/tmp/{}.json".format(config)
        render_template_to_host(template_name, duthost, dest_path, dash_smartswitch_vnet_config, op=op)
        if ENABLE_GNMI_API:
            apply_gnmi_file(localhost, duthost, ptfhost, dest_path, None, 5, 1024, host)
        else:
            apply_swssconfig_file(duthost, dest_path)

    yield

    # Route rule removal is broken so config reload to cleanup for now
    # https://github.com/sonic-net/sonic-buildimage/issues/23590
    config_reload(dpuhost, safe_reload=True, yang_validate=False)


def test_smartswitch_outbound_vnet(
        ptfadapter,
        dash_smartswitch_vnet_config,
        skip_dataplane_checking,
        inner_packet_type):

    if skip_dataplane_checking:
        return
    _, vxlan_packet, expected_packet = packets.outbound_smartswitch_vnet_packets(dash_smartswitch_vnet_config,
                                                                                 inner_packet_type=inner_packet_type)
    ptfadapter.dataplane.flush()
    testutils.send(ptfadapter, dash_smartswitch_vnet_config[LOCAL_PTF_INTF], vxlan_packet, 1)
    testutils.verify_packets_any(ptfadapter, expected_packet, ports=dash_smartswitch_vnet_config[REMOTE_PTF_RECV_INTF])
