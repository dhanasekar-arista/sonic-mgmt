"""
Module: tests.dash
File: test_plnsg.py
Description:
    DASH PrivateLink Network Security Group (PL NSG) test suite for SmartSwitch topology.
    This module validates bi-directional traffic transformation with NSG-specific tunnel
    configurations and VXLAN UDP source port range validation for PrivateLink scenarios.

Test Intent:
    - Validate PrivateLink NSG outbound traffic transformation (VM -> PE)
    - Verify PrivateLink NSG inbound traffic transformation (PE -> VM)
    - Test VXLAN UDP source port range compliance for return traffic
    - Ensure proper encapsulation with NSG-specific tunnel endpoints
    - Validate single-endpoint tunnel configuration (multi-endpoint not yet supported)

Topology:
    - smartswitch: SmartSwitch topology with DPU-NPU architecture
    - Requires NPU static routes and DPU-NPU dataplane setup
    - Traffic flows: VM <-> DPU <-> PE with NSG tunnel endpoints

Fixtures Used:
    - localhost: Ansible localhost for configuration management
    - duthost: Device Under Test (NPU) host object
    - ptfhost: PTF (Packet Test Framework) host
    - ptfadapter: PTF adapter for packet injection/verification
    - dpuhosts: List of DPU host objects
    - dpu_index: Index of DPU to use for testing
    - dash_pl_config: PrivateLink DASH configuration
    - skip_config: Flag to skip configuration application
    - single_endpoint: Parameterized fixture (currently only True supported)
    - set_vxlan_udp_sport_range: Fixture to configure VXLAN UDP source port range
    - setup_npu_dpu: Combined fixture for NPU and DPU setup
    - config_setup_teardown: Main setup/teardown with NSG-specific DASH configs

Dependencies:
    - configs.privatelink_config: PrivateLink configuration constants
    - constants: DASH test constants (ports, IPs, VXLAN parameters)
    - gnmi_utils: gNMI utilities for protobuf message application
    - packets: Packet generation (inbound_pl_packets, plnsg_packets)
    - test_fnic: Shared utility (verify_tunnel_packets)
    - tests.common.config_reload: Configuration reload utilities

Notes:
    - Currently only supports single-endpoint configuration
    - Multi-endpoint configuration skipped: "Multiple tunnel endpoints not yet supported for PL NSG"
    - VXLAN UDP source port validated to be in range [BASE_SRC_PORT, BASE_SRC_PORT + 2^MASK - 1]
    - Tunnel endpoints use TUNNEL3_CONFIG for single-endpoint (TUNNEL4_CONFIG for multi)
    - NSG-specific VNET mapping: PE_PLNSG_SINGLE_ENDPOINT_VNET_MAPPING_CONFIG
    - Inbound routing not implemented in Pensando SAI (route rules conditionally applied)
    - Config reload used for cleanup due to route rule removal bug
    - Related GitHub issue: https://github.com/sonic-net/sonic-buildimage/issues/23590
    - Return packet payload updated to include test metadata
    - VXLAN sport range enforced: VXLAN_UDP_BASE_SRC_PORT with VXLAN_UDP_SRC_PORT_MASK

Git History (last 1 commit):
    12abd5cea [dash] Add tests to cover PLNSG, FNIC, trusted VNI, return path ECMP (#19700)
"""

import logging
import configs.privatelink_config as pl
import ptf.testutils as testutils
from tests.common.config_reload import config_reload
import pytest
from constants import (
    LOCAL_PTF_INTF,
    REMOTE_PTF_RECV_INTF,
    REMOTE_PTF_SEND_INTF,
    VXLAN_UDP_BASE_SRC_PORT,
    VXLAN_UDP_SRC_PORT_MASK,
)
from gnmi_utils import apply_messages
from packets import inbound_pl_packets, plnsg_packets
from tests.common.dash_utils import verify_tunnel_packets
from tests.common.helpers.assertions import pytest_assert as pt_assert
import ptf.packet as scapy

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('smartswitch')
]


@pytest.fixture(autouse=True)
def config_setup_teardown(
    localhost,
    duthost,
    ptfhost,
    dpu_index,
    skip_config,
    dpuhosts,
    single_endpoint,
    set_vxlan_udp_sport_range,
    setup_npu_dpu  # noqa :F811
):
    if not single_endpoint:
        pytest.skip("Multiple tunnel endpoints not yet supported for PL NSG")

    if skip_config:
        yield
        return
    dpuhost = dpuhosts[dpu_index]
    logger.info(pl.ROUTING_TYPE_PL_CONFIG)

    if single_endpoint:
        tunnel_config = pl.TUNNEL3_CONFIG
    else:
        tunnel_config = pl.TUNNEL4_CONFIG

    base_config_messages = {
        **pl.APPLIANCE_CONFIG,
        **pl.ROUTING_TYPE_PL_CONFIG,
        **pl.ROUTING_TYPE_VNET_CONFIG,
        **pl.VNET_CONFIG,
        **pl.VNET2_CONFIG,
        **pl.ROUTE_GROUP1_CONFIG,
        **pl.METER_POLICY_V4_CONFIG,
        **tunnel_config,
    }
    logger.info(base_config_messages)

    apply_messages(localhost, duthost, ptfhost, base_config_messages, dpuhost.dpu_index)

    if single_endpoint:
        vnet_mapping_config = pl.PE_PLNSG_SINGLE_ENDPOINT_VNET_MAPPING_CONFIG
    else:
        vnet_mapping_config = pl.PE_PLNSG_MULTI_ENDPOINT_VNET_MAPPING_CONFIG
    route_and_mapping_messages = {
        **vnet_mapping_config,
        **pl.PE_SUBNET_ROUTE_CONFIG,
        **pl.VM_SUBNET_ROUTE_CONFIG,
    }
    logger.info(route_and_mapping_messages)
    apply_messages(localhost, duthost, ptfhost, route_and_mapping_messages, dpuhost.dpu_index)

    if 'pensando' not in dpuhost.facts['asic_type']:
        route_rule_messages = {
            **pl.VM_VNI_ROUTE_RULE_CONFIG,
            **pl.INBOUND_VNI_ROUTE_RULE_CONFIG,
        }
        logger.info(route_rule_messages)
        apply_messages(localhost, duthost, ptfhost, route_rule_messages, dpuhost.dpu_index)

    meter_rule_messages = {
        **pl.METER_RULE1_V4_CONFIG,
        **pl.METER_RULE2_V4_CONFIG,
    }
    logger.info(meter_rule_messages)
    apply_messages(localhost, duthost, ptfhost, meter_rule_messages, dpuhost.dpu_index)

    logger.info(pl.ENI_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl.ENI_CONFIG, dpuhost.dpu_index)

    logger.info(pl.ENI_ROUTE_GROUP1_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl.ENI_ROUTE_GROUP1_CONFIG, dpuhost.dpu_index)

    yield

    # Route rule removal is broken so config reload to cleanup for now
    # https://github.com/sonic-net/sonic-buildimage/issues/23590
    config_reload(dpuhost, safe_reload=True, yang_validate=False)


def test_privatelink_nsg(
    ptfadapter,
    dash_pl_config,
    single_endpoint
):
    vm_to_dpu_pkt, exp_dpu_to_pe_pkt = plnsg_packets(dash_pl_config)
    pe_to_dpu_pkt, exp_dpu_to_vm_pkt = inbound_pl_packets(dash_pl_config)

    exp_dpu_to_pe_pkt = ptfadapter.update_payload(exp_dpu_to_pe_pkt)

    ptfadapter.dataplane.flush()
    if single_endpoint:
        tunnel_endpoint_counts = {ip: 0 for ip in pl.TUNNEL3_ENDPOINT_IPS}
    else:
        tunnel_endpoint_counts = {ip: 0 for ip in pl.TUNNEL4_ENDPOINT_IPS}
    testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], vm_to_dpu_pkt, 1)
    verify_tunnel_packets(ptfadapter, dash_pl_config[REMOTE_PTF_RECV_INTF], exp_dpu_to_pe_pkt, tunnel_endpoint_counts)
    testutils.send(ptfadapter, dash_pl_config[REMOTE_PTF_SEND_INTF], pe_to_dpu_pkt, 1)

    exp_dpu_to_vm_pkt = ptfadapter.update_payload(exp_dpu_to_vm_pkt)
    result = testutils.dp_poll(ptfadapter, timeout=1, exp_pkt=exp_dpu_to_vm_pkt)
    if isinstance(result, ptfadapter.dataplane.PollSuccess):
        pkt_repr = scapy.Ether(result.packet)
        sport = pkt_repr[scapy.UDP].sport
        port_range_end = VXLAN_UDP_BASE_SRC_PORT + (1 << VXLAN_UDP_SRC_PORT_MASK) - 1
        pt_assert(
            VXLAN_UDP_BASE_SRC_PORT <= sport <= port_range_end,
            f"VXLAN source port {sport} not in expected range {VXLAN_UDP_BASE_SRC_PORT}-{port_range_end}",
        )
