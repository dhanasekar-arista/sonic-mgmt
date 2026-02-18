"""
Module: tests.dash
File: test_relaxed_match_negative.py
Description:
    DASH relaxed match negative test suite for DPU topology. This module validates
    the dynamic VXLAN UDP destination port configuration feature by testing packet
    forwarding/dropping behavior when the configured port changes at runtime.

Test Intent:
    - Validate relaxed match VXLAN UDP dst port feature
    - Test dynamic port reconfiguration behavior
    - Verify packet forwarding with default port (4789)
    - Verify packet dropping when port changes
    - Test port restoration and forwarding recovery
    - Ensure packets with non-configured ports are dropped

Topology:
    - dpu: DPU topology for DASH testing
    - Skips "with-underlay-route" scenarios (not needed for port config testing)

Fixtures Used:
    - duthost: Device Under Test (DPU) host object
    - ptfadapter: PTF adapter for packet injection/verification
    - apply_vnet_configs: Fixture to apply VNET DASH configurations
    - dash_config_info: DASH configuration information dictionary
    - acl_default_rule: Fixture for default ACL rule configuration
    - restore_vxlan_udp_dport: Fixture to restore port to 4789 after test
    - skip_underlay_route: Auto-used fixture to skip underlay route tests

Dependencies:
    - constants: DASH test constants (LOCAL_PTF_INTF, REMOTE_PTF_INTF)
    - tests.common.plugins.allure_wrapper: Allure reporting with test steps
    - tests.dash.conftest: config_vxlan_udp_dport utility function
    - packets: Packet generation utilities (outbound_vnet_packets)
    - ptf.testutils: PTF packet testing utilities

Notes:
    - Test uses allure.step for detailed step-by-step reporting
    - Default VXLAN UDP dst port: 4789
    - Test port changed to: 13330
    - Port configuration applied via swssconfig (SWITCH_TABLE:switch)
    - Restoration ensures DPU returns to default state (4789)
    - Underlay route scenarios skipped as unnecessary for this test
    - Four test phases:
      1. Verify forwarding with default port 4789
      2. Change to 13330, verify 4789 packets dropped
      3. Restore to 4789, verify forwarding works again
      4. Verify packets with port 13330 are dropped

Git History (last 1 commit):
    24668cbd0 [Dash] Relaxed match support (#11630)
"""

import logging
import pytest
import ptf.testutils as testutils

from constants import LOCAL_PTF_INTF, REMOTE_PTF_INTF
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.dash.conftest import config_vxlan_udp_dport
import packets

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('dpu'),
]


@pytest.fixture(autouse=True)
def skip_underlay_route(request):
    if 'with-underlay-route' in request.node.name:
        pytest.skip('Skip the test with param "with-underlay-route", '
                    'it is unnecessary to cover all underlay route scenarios.')


@pytest.fixture()
def restore_vxlan_udp_dport(duthost):

    yield

    config_vxlan_udp_dport(duthost, 4789)


def test_relaxed_match_negative(duthost, ptfadapter, apply_vnet_configs, dash_config_info,
                                acl_default_rule, restore_vxlan_udp_dport):
    """
    Negative test of dynamically changing the VxLAN UDP dst port
    """
    with allure.step("Check the traffic with default port 4789 is forwarded by the DPU"):
        _, vxlan_packet, expected_packet = packets.outbound_vnet_packets(dash_config_info)
        testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
        testutils.verify_packets_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])
    with allure.step("Change the port to 13330, check the packet with port 4789 is dropped"):
        config_vxlan_udp_dport(duthost, 13330)
        testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
        testutils.verify_no_packet_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])
    with allure.step("Change the port back to 4789, check the packet with port 4789 is forwarded"):
        config_vxlan_udp_dport(duthost, 4789)
        testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
        testutils.verify_packets_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])
    with allure.step("Check the packet with port 13330 is dropped"):
        _, vxlan_packet, expected_packet = packets.outbound_vnet_packets(dash_config_info, vxlan_udp_dport=13330)
        testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
        testutils.verify_no_packet_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])
