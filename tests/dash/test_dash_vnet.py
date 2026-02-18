"""
Module: tests.dash
File: test_dash_vnet.py
Description:
    DASH VNET test suite for DPU topology. This module validates outbound and inbound
    VNET traffic transformation, including vnet, vnet_direct, and direct routing modes,
    as well as PA (Provider Address) validation for inbound traffic.

Test Intent:
    - Validate outbound VNET routing with VXLAN encapsulation
    - Test outbound VNET direct routing with overlay IP lookup
    - Verify outbound direct routing (without VNET encapsulation)
    - Test inbound VNET with PA validation (match and mismatch scenarios)
    - Verify ASIC DB entries for VNET and ENI objects
    - Ensure proper packet transformation for multiple inner packet types
    - Test configurable VXLAN UDP destination port

Topology:
    - dpu: DPU topology for DASH testing
    - Requires DASH VNET configuration applied via fixtures

Fixtures Used:
    - ptfadapter: PTF adapter for packet injection/verification
    - apply_vnet_configs: Applies VNET routing configuration
    - apply_vnet_direct_configs: Applies VNET direct routing configuration
    - apply_direct_configs: Applies direct routing configuration
    - apply_inbound_configs: Applies inbound VNET configuration
    - dash_config_info: DASH configuration information dictionary
    - skip_dataplane_checking: Flag to skip dataplane verification
    - asic_db_checker: Fixture to verify ASIC DB entries
    - inner_packet_type: Parameterized inner packet type (udp/tcp/echo_request/echo_reply)
    - acl_default_rule: Default ACL rule configuration
    - vxlan_udp_dport: Configurable VXLAN UDP destination port

Dependencies:
    - constants: DASH test constants (LOCAL_PTF_INTF, REMOTE_PTF_INTF)
    - packets: Packet generation utilities (outbound_vnet_packets, inbound_vnet_packets)
    - ptf.testutils: PTF packet testing utilities
    - pytest: Testing framework with markers

Notes:
    - Log analyzer disabled for this test suite
    - ASIC DB verification checks for SAI_OBJECT_TYPE_VNET and SAI_OBJECT_TYPE_ENI
    - Inner packet types tested: UDP, TCP, ICMP echo request, ICMP echo reply
    - Outbound vnet: VM VNI -> Remote VNI with VXLAN encapsulation
    - Outbound vnet_direct: Uses maprouting with overlay IP lookup (1.1.1.1)
    - Outbound direct: No VNET encapsulation, direct IP forwarding
    - Inbound PA validation: Tests both matching and mismatching source PA
    - PA mismatch packets expected to be dropped (no verification packet sent)
    - VXLAN UDP dport configurable via --vxlan_udp_dport parameter
    - Default ACL rules may be required on specific hardware (Nvidia DPUs)

Git History (last 10 commits):
    24668cbd0 [Dash] Relaxed match support (#11630)
    dab77c420 Remove TACACS fixture from none TACACS test cases (#13422)
    07f328770 Enable TACACS on test cases. (#12433)
    e5e678fba Align dash tests to support DPU with one single port (#11394)
    3657b8878 [Dash] Enhance the dash vnet test to support tcp and icmp packets (#10904)
    d7371c53c [dash]: Add test cases for DASH ACL (#7848)
    5ea2dc657 DPU test cases with GNMI and Protobuf (#9238)
    513c9ecb9 [topo]: Rename topology appliance to dpu (#9901)
    49a21a19d [dash] Add VNET direct and direct routing tests (#8072)
    5733ca7fe [pre-commit] Fix style issues in test scripts (#8001)
"""

import logging
import pytest
import ptf.testutils as testutils
import packets

from constants import LOCAL_PTF_INTF, REMOTE_PTF_INTF

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('dpu'),
    pytest.mark.disable_loganalyzer
]


def test_outbound_vnet(
        ptfadapter,
        apply_vnet_configs,
        dash_config_info,
        skip_dataplane_checking,
        asic_db_checker,
        inner_packet_type,
        acl_default_rule,
        vxlan_udp_dport):
    """
    Send VXLAN packets from the VM VNI
    """
    asic_db_checker(["SAI_OBJECT_TYPE_VNET", "SAI_OBJECT_TYPE_ENI"])
    if skip_dataplane_checking:
        return
    _, vxlan_packet, expected_packet = packets.outbound_vnet_packets(dash_config_info,
                                                                     vxlan_udp_dport=vxlan_udp_dport,
                                                                     inner_packet_type=inner_packet_type)
    testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
    testutils.verify_packets_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])
    # testutils.verify_packet(ptfadapter, expected_packet, dash_config_info[REMOTE_PTF_INTF])


def test_outbound_vnet_direct(
        ptfadapter,
        apply_vnet_direct_configs,
        dash_config_info,
        skip_dataplane_checking,
        asic_db_checker,
        inner_packet_type,
        acl_default_rule,
        vxlan_udp_dport):
    asic_db_checker(["SAI_OBJECT_TYPE_VNET", "SAI_OBJECT_TYPE_ENI"])
    if skip_dataplane_checking:
        return
    _, vxlan_packet, expected_packet = packets.outbound_vnet_packets(dash_config_info,
                                                                     vxlan_udp_dport=vxlan_udp_dport,
                                                                     inner_packet_type=inner_packet_type)
    testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
    testutils.verify_packets_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])
    # testutils.verify_packet(ptfadapter, expected_packet, dash_config_info[REMOTE_PTF_INTF])


def test_outbound_direct(
        ptfadapter,
        apply_direct_configs,
        dash_config_info,
        skip_dataplane_checking,
        asic_db_checker,
        inner_packet_type,
        acl_default_rule,
        vxlan_udp_dport):
    asic_db_checker(["SAI_OBJECT_TYPE_VNET", "SAI_OBJECT_TYPE_ENI"])
    if skip_dataplane_checking:
        return
    expected_inner_packet, vxlan_packet, _ = packets.outbound_vnet_packets(dash_config_info,
                                                                           vxlan_udp_dport=vxlan_udp_dport,
                                                                           inner_packet_type=inner_packet_type)
    testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
    testutils.verify_packets_any(ptfadapter, expected_inner_packet, ports=dash_config_info[REMOTE_PTF_INTF])
    # testutils.verify_packet(ptfadapter, expected_inner_packet, dash_config_info[REMOTE_PTF_INTF])


def test_inbound_vnet_pa_validate(
        ptfadapter,
        apply_inbound_configs,
        dash_config_info,
        skip_dataplane_checking,
        asic_db_checker,
        inner_packet_type,
        acl_default_rule,
        vxlan_udp_dport):
    """
    Send VXLAN packets from the remote VNI with PA validation enabled

    1. Send one packet where the source PA (outer source IP) matches the VNET mapping table
        - Expect DPU to forward packet normally
    2. Send one packet where the source PA does not match the mapping table
        - Expect DPU to drop packet
    """
    asic_db_checker(["SAI_OBJECT_TYPE_VNET", "SAI_OBJECT_TYPE_ENI"])
    if skip_dataplane_checking:
        return
    _,  pa_match_packet, pa_mismatch_packet, expected_packet = packets.inbound_vnet_packets(
        dash_config_info, vxlan_udp_dport=vxlan_udp_dport, inner_packet_type=inner_packet_type)
    testutils.send(ptfadapter, dash_config_info[REMOTE_PTF_INTF], pa_match_packet, 1)
    testutils.verify_packets_any(ptfadapter, expected_packet, ports=dash_config_info[LOCAL_PTF_INTF])
    testutils.send(ptfadapter, dash_config_info[REMOTE_PTF_INTF], pa_mismatch_packet, 1)
