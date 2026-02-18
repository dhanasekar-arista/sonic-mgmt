"""
Module: tests.dash
File: test_fnic.py
Description:
    DASH Floating NIC (FNIC) test suite for SmartSwitch topology. This module validates
    bi-directional traffic flow through floating NICs with PrivateLink configuration,
    including outbound VM-to-PE traffic and inbound PE-to-VM return traffic with tunnel
    endpoint ECMP distribution testing.

Test Intent:
    - Validate Floating NIC (FNIC) functionality on SmartSwitch DPU
    - Test bi-directional traffic transformation (VM <-> PE)
    - Verify tunnel endpoint ECMP distribution for multi-endpoint configurations
    - Validate proper encapsulation/decapsulation with trusted VNI
    - Test single-endpoint and multi-endpoint tunnel configurations
    - Ensure packet distribution across multiple tunnel endpoints is balanced

Topology:
    - smartswitch: SmartSwitch topology with DPU-NPU architecture
    - Requires DPU-NPU dataplane interface IP assignments
    - Neighbor info must be learned on DPU dataplane port before DASH config
    - Traffic flows: VM <-> DPU <-> PE (bi-directional)

Fixtures Used:
    - localhost: Ansible localhost for configuration management
    - duthost: Device Under Test (NPU) host object
    - ptfhost: PTF (Packet Test Framework) host
    - ptfadapter: PTF adapter for packet injection/verification
    - dpuhosts: List of DPU host objects
    - dpu_index: Index of DPU to use for testing
    - dash_pl_config: PrivateLink DASH configuration
    - skip_config: Flag to skip configuration application
    - set_vxlan_udp_sport_range: Fixture to configure VXLAN UDP source port range
    - setup_npu_dpu: Combined fixture for NPU and DPU setup
    - single_endpoint: Parameterized fixture for single vs multi-endpoint testing
    - common_setup_teardown: Main setup/teardown with FNIC-specific DASH configs

Dependencies:
    - configs.privatelink_config: PrivateLink configuration constants
    - constants: DASH test constants
    - gnmi_utils: gNMI utilities for configuration via protobuf messages
    - packets: Packet generation utilities (rand_udp_port_packets)
    - tests.dash.dash_utils: DASH-specific utilities (verify_tunnel_packets)
    - tests.common.config_reload: Configuration reload utilities

Notes:
    - Neighbor info learning is automatic via default route application
    - orchagent resolves next hop IP to learn neighbor information
    - Single-endpoint: 5 packets tested, validates basic functionality
    - Multi-endpoint: 1000 packets tested to verify ECMP distribution
    - Expected packet distribution: +/- 25% of average per tunnel endpoint
    - Inbound routing not implemented in Pensando SAI (route rules skipped)
    - Config reload used for cleanup due to route rule removal bug
    - Related GitHub issue: https://github.com/sonic-net/sonic-buildimage/issues/23590
    - Payload updated for return packets to include test metadata

Git History (last 2 commits):
    2c20c10f5 [DASH] Need to avoid skipping the dash tests on smartswitch (#20958)
    12abd5cea [dash] Add tests to cover PLNSG, FNIC, trusted VNI, return path ECMP (#19700)
"""

import logging

import configs.privatelink_config as pl
import ptf.testutils as testutils
import pytest
from constants import LOCAL_PTF_INTF, REMOTE_PTF_RECV_INTF, REMOTE_PTF_SEND_INTF
from gnmi_utils import apply_messages
from packets import rand_udp_port_packets
from tests.common import config_reload

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology("smartswitch"),
    pytest.mark.skip_check_dut_health
]


@pytest.fixture(autouse=True)
def common_setup_teardown(
    localhost,
    duthost,
    ptfhost,
    dpu_index,
    skip_config,
    dpuhosts,
    set_vxlan_udp_sport_range,
    # manually invoke setup_npu_dpu to ensure routes are added before DASH configs are programmed
    setup_npu_dpu,  # noqa: F811
):
    if skip_config:
        yield
        return
    dpuhost = dpuhosts[dpu_index]
    logger.info(pl.ROUTING_TYPE_PL_CONFIG)

    base_config_messages = {
        **pl.APPLIANCE_FNIC_CONFIG,
        **pl.ROUTING_TYPE_PL_CONFIG,
        **pl.ROUTING_TYPE_VNET_CONFIG,
        **pl.VNET_CONFIG,
        **pl.ROUTE_GROUP1_CONFIG,
        **pl.METER_POLICY_V4_CONFIG,
    }
    logger.info(base_config_messages)

    apply_messages(localhost, duthost, ptfhost, base_config_messages, dpuhost.dpu_index)

    route_and_mapping_messages = {
        **pl.PE_VNET_MAPPING_CONFIG,
        **pl.PE_SUBNET_ROUTE_CONFIG,
        **pl.VM_VNET_MAPPING_CONFIG,
        **pl.VM_SUBNET_ROUTE_CONFIG
    }
    logger.info(route_and_mapping_messages)
    apply_messages(localhost, duthost, ptfhost, route_and_mapping_messages, dpuhost.dpu_index)

    # inbound routing not implemented in Pensando SAI yet, so skip route rule programming
    if 'pensando' not in dpuhost.facts['asic_type']:
        route_rule_messages = {
            **pl.VM_VNI_ROUTE_RULE_CONFIG,
            **pl.INBOUND_VNI_ROUTE_RULE_CONFIG,
            **pl.TRUSTED_VNI_ROUTE_RULE_CONFIG
        }
        logger.info(route_rule_messages)
        apply_messages(localhost, duthost, ptfhost, route_rule_messages, dpuhost.dpu_index)

    logger.info(pl.ENI_FNIC_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl.ENI_FNIC_PL_CONFIG, dpuhost.dpu_index)

    logger.info(pl.ENI_ROUTE_GROUP1_CONFIG)
    apply_messages(localhost, duthost, ptfhost, pl.ENI_ROUTE_GROUP1_CONFIG, dpuhost.dpu_index)

    yield

    # Route rule removal is broken so config reload to cleanup for now
    # https://github.com/sonic-net/sonic-buildimage/issues/23590
    if 'pensando' in dpuhost.facts['asic_type']:
        apply_messages(localhost, duthost, ptfhost, pl.ENI_ROUTE_GROUP1_CONFIG, dpuhost.dpu_index, False)
        apply_messages(localhost, duthost, ptfhost, pl.ENI_FNIC_CONFIG, dpuhost.dpu_index, False)
        apply_messages(localhost, duthost, ptfhost, route_and_mapping_messages, dpuhost.dpu_index, False)
        apply_messages(localhost, duthost, ptfhost, base_config_messages, dpuhost.dpu_index, False)
    else:
        config_reload(dpuhost, safe_reload=True, yang_validate=False)


@pytest.mark.parametrize("encap_proto", ["vxlan", "gre"])
def test_fnic(ptfadapter, dash_pl_config, encap_proto):
    num_packets = 5
    pkt_sets = list()

    for _ in range(num_packets):
        vm_to_dpu_pkt, exp_dpu_to_pe_pkt, pe_to_dpu_pkt, exp_dpu_to_vm_pkt = rand_udp_port_packets(
            dash_pl_config, floating_nic=True, outbound_vni=pl.VNET1_VNI, outbound_encap=encap_proto
        )
        pkt_sets.append((vm_to_dpu_pkt, exp_dpu_to_pe_pkt, pe_to_dpu_pkt, exp_dpu_to_vm_pkt))

    ptfadapter.dataplane.flush()
    for vm_to_dpu_pkt, exp_dpu_to_pe_pkt, pe_to_dpu_pkt, exp_dpu_to_vm_pkt in pkt_sets:
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], vm_to_dpu_pkt, 1)
        testutils.verify_packet_any_port(ptfadapter, exp_dpu_to_pe_pkt, dash_pl_config[REMOTE_PTF_RECV_INTF])
        testutils.send(ptfadapter, dash_pl_config[REMOTE_PTF_SEND_INTF], pe_to_dpu_pkt, 1)
        testutils.verify_packet(ptfadapter, exp_dpu_to_vm_pkt, dash_pl_config[LOCAL_PTF_INTF])
