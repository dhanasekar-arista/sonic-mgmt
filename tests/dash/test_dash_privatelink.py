"""
Module: tests.dash
File: test_dash_privatelink.py
Description:
    DASH PrivateLink test suite for SmartSwitch topology. This module validates
    bi-directional traffic transformation for PrivateLink scenarios with both VXLAN
    and GRE encapsulation, including VXLAN UDP source port range validation.

Test Intent:
    - Validate PrivateLink outbound traffic transformation (VM -> PE)
    - Test PrivateLink inbound traffic transformation (PE -> VM)
    - Verify VXLAN and GRE encapsulation support
    - Test VXLAN UDP source port range compliance
    - Validate negative scenario: packets outside configured sport range dropped
    - Ensure proper routing through NPU static routes and DPU setup

Topology:
    - smartswitch: SmartSwitch topology with DPU-NPU architecture
    - Requires DPU-NPU dataplane interface IP assignments
    - Traffic flows: VM <-> DPU <-> PE with PrivateLink configuration

Fixtures Used:
    - localhost: Ansible localhost for configuration management
    - duthost: Device Under Test (NPU) host object
    - ptfhost: PTF (Packet Test Framework) host
    - ptfadapter: PTF adapter for packet injection/verification
    - dpuhosts: List of DPU host objects
    - dpu_index: Index of DPU to use for testing
    - dpuhost: DPU host object (from dpuhosts[dpu_index])
    - dash_pl_config: PrivateLink DASH configuration
    - skip_config: Flag to skip configuration application
    - set_vxlan_udp_sport_range: Fixture to configure VXLAN UDP source port range
    - setup_npu_dpu: Combined fixture for NPU and DPU setup
    - common_setup_teardown: Main setup/teardown with PrivateLink DASH configs
    - encap_proto: Parameterized encapsulation protocol (vxlan/gre)

Dependencies:
    - configs.privatelink_config: PrivateLink configuration constants
    - constants: DASH test constants (ports, IPs, VXLAN parameters)
    - gnmi_utils: gNMI utilities for protobuf message application
    - packets: Packet generation (outbound_pl_packets, inbound_pl_packets)
    - tests.common.config_reload: Configuration reload utilities

Notes:
    - DPU-NPU dataplane interfaces must have IPs assigned before testing
    - VXLAN UDP source port range: [BASE_SRC_PORT, BASE_SRC_PORT + 2^MASK - 1]
    - Default range: 5120-5247 (BASE=5120, MASK=7, range=128 ports)
    - Negative test validates 6 invalid sport values across the range
    - Invalid sport examples: 1, random(2 to min-2), min-1, max+1, random(max+2 to 65534), 65535
    - Config reload used for cleanup to avoid route rule removal issues
    - Encapsulation protocols tested: VXLAN and GRE (parameterized)
    - Bi-directional validation: outbound (VM->PE) and inbound (PE->VM)
    - Packets verified on correct egress ports with proper transformation

Git History (last 10 commits):
    352f4432d [DASH] Add a new test case to cover the negative scenario of PL VXLAN UDP source port range (#21145)
    2c20c10f5 [DASH] Need to avoid skipping the dash tests on smartswitch (#20958)
    12abd5cea [dash] Add tests to cover PLNSG, FNIC, trusted VNI, return path ECMP (#19700)
    560d76137 Test plan and test for feature VXLAN source port range (#18789)
    7404723f9 algin pl tests (#18303)
    05aa9ff5c [DASH] SS changes to privatelink test for smartswitch (#17324)
    8c888ce7a DASH PL tests fixes (#17881)
    d39d7f8bb Add Dash meter class, policy, rule config to PL tests (#17884)
    48edf5b91 add smartswitch vnet2vnet DASH tests (#17042)
    162845002 [dash] Add Privatelink traffic test (#14757)
"""

import logging

import configs.privatelink_config as pl
import ptf.testutils as testutils
import pytest
import random
import ptf.packet as scapy
from constants import LOCAL_PTF_INTF, REMOTE_PTF_RECV_INTF, REMOTE_PTF_SEND_INTF
from constants import VXLAN_UDP_BASE_SRC_PORT, VXLAN_UDP_SRC_PORT_MASK
from gnmi_utils import apply_messages
from packets import outbound_pl_packets, inbound_pl_packets
from tests.common.config_reload import config_reload

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('smartswitch'),
    pytest.mark.skip_check_dut_health
]


@pytest.fixture(autouse=True, scope="function")
def common_setup_teardown(
    localhost,
    duthost,
    ptfhost,
    dpu_index,
    skip_config,
    dpuhosts,
    set_vxlan_udp_sport_range,
    setup_npu_dpu  # noqa: F811
):
    if skip_config:
        return
    dpuhost = dpuhosts[dpu_index]
    logger.info(pl.ROUTING_TYPE_PL_CONFIG)
    base_config_messages = {
        **pl.APPLIANCE_CONFIG,
        **pl.ROUTING_TYPE_PL_CONFIG,
        **pl.VNET_CONFIG,
        **pl.ROUTE_GROUP1_CONFIG,
        **pl.METER_POLICY_V4_CONFIG
    }
    logger.info(base_config_messages)

    apply_messages(localhost, duthost, ptfhost, base_config_messages, dpuhost.dpu_index)

    route_and_mapping_messages = {
        **pl.PE_VNET_MAPPING_CONFIG,
        **pl.PE_SUBNET_ROUTE_CONFIG,
        **pl.VM_SUBNET_ROUTE_CONFIG
    }

    if 'bluefield' in dpuhost.facts['asic_type']:
        route_and_mapping_messages.update({
            **pl.INBOUND_VNI_ROUTE_RULE_CONFIG
        })

    logger.info(route_and_mapping_messages)
    apply_messages(localhost, duthost, ptfhost, route_and_mapping_messages, dpuhost.dpu_index)

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

    config_reload(dpuhost, safe_reload=True, yang_validate=False)
    # apply_messages(localhost, duthost, ptfhost, pl.ENI_ROUTE_GROUP1_CONFIG, dpuhost.dpu_index, False)
    # apply_messages(localhost, duthost, ptfhost, pl.ENI_CONFIG, dpuhost.dpu_index, False)
    # apply_messages(localhost, duthost, ptfhost, meter_rule_messages, dpuhost.dpu_index, False)
    # apply_messages(localhost, duthost, ptfhost, route_and_mapping_messages, dpuhost.dpu_index, False)
    # apply_messages(localhost, duthost, ptfhost, base_config_messages, dpuhost.dpu_index, False)


@pytest.mark.parametrize("encap_proto", ["vxlan", "gre"])
def test_privatelink_basic_transform(
    ptfadapter,
    dash_pl_config,
    encap_proto
):
    vm_to_dpu_pkt, exp_dpu_to_pe_pkt = outbound_pl_packets(dash_pl_config, encap_proto)
    pe_to_dpu_pkt, exp_dpu_to_vm_pkt = inbound_pl_packets(dash_pl_config)

    ptfadapter.dataplane.flush()
    testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], vm_to_dpu_pkt, 1)
    testutils.verify_packet_any_port(ptfadapter, exp_dpu_to_pe_pkt, dash_pl_config[REMOTE_PTF_RECV_INTF])
    testutils.send(ptfadapter, dash_pl_config[REMOTE_PTF_SEND_INTF], pe_to_dpu_pkt, 1)
    testutils.verify_packet(ptfadapter, exp_dpu_to_vm_pkt, dash_pl_config[LOCAL_PTF_INTF])


@pytest.mark.parametrize("vxlan_security", ["true", "false"])
def test_privatelink_udp_sport_range_negative(
    ptfadapter,
    dash_pl_config,
    vxlan_security,
    request
):
    """
    Validate that when the VXLAN UDP source port is not in the configured
    range, the packet is dropped by the DPU when vxlan_security is true.
    When vxlan_security is false, the packet is not dropped.
    """
    # vxlan_security is enabled by default, disable it when vxlan_security is false
    if vxlan_security == "false":
        request.getfixturevalue("disable_vxlan_security")

    vm_to_dpu_pkt, exp_dpu_to_pe_pkt = outbound_pl_packets(dash_pl_config, "vxlan")
    min_valid_sport = VXLAN_UDP_BASE_SRC_PORT
    max_valid_sport = VXLAN_UDP_BASE_SRC_PORT + 2**VXLAN_UDP_SRC_PORT_MASK - 1
    invalid_sport_list = [1,
                          random.randint(2, min_valid_sport - 2),
                          min_valid_sport - 1,
                          max_valid_sport + 1,
                          random.randint(max_valid_sport + 2, 65534),
                          65535]
    logger.info(f"Send the vxlan encaped outbound packets with invalid sport: \
        {invalid_sport_list}")

    logger.info(f"Validate the traffic when vxlan_security is {vxlan_security}.")
    for invalid_sport in invalid_sport_list:
        vm_to_dpu_pkt[scapy.UDP].sport = invalid_sport
        ptfadapter.dataplane.flush()
        logger.info(f"Sending packet with sport: {invalid_sport}")
        testutils.send(ptfadapter, dash_pl_config[LOCAL_PTF_INTF], vm_to_dpu_pkt, 1)
        if vxlan_security == "true":
            logger.info("Check the packet is dropped.")
            testutils.verify_no_packet_any(ptfadapter, exp_dpu_to_pe_pkt, dash_pl_config[REMOTE_PTF_RECV_INTF])
        else:
            logger.info("Check the packet is not dropped.")
            testutils.verify_packet_any_port(ptfadapter, exp_dpu_to_pe_pkt, dash_pl_config[REMOTE_PTF_RECV_INTF])
