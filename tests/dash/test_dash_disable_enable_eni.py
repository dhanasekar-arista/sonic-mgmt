"""
Module: tests.dash
File: test_dash_disable_enable_eni.py
Description:
    DASH ENI admin state control test suite for DPU topology. This module validates
    the dynamic enable/disable functionality of ENI (Elastic Network Interface) and
    verifies that traffic is properly dropped when ENI is disabled and forwarded
    when ENI is enabled.

Test Intent:
    - Validate ENI admin state configuration via gNMI
    - Verify traffic forwarding when ENI is enabled
    - Test traffic dropping when ENI is disabled
    - Validate ASIC_DB ENI admin state attribute updates
    - Ensure state transitions (enabled -> disabled -> enabled) work correctly
    - Test end-to-end traffic impact of ENI state changes

Topology:
    - dpu: DPU topology for DASH testing
    - Skips "with-underlay-route" scenarios (not needed for ENI state testing)

Fixtures Used:
    - ptfadapter: PTF adapter for packet injection/verification
    - localhost: Ansible localhost for configuration management
    - duthost: Device Under Test (DPU) host object
    - ptfhost: PTF host for gNMI configuration
    - apply_vnet_configs: Applies VNET routing configuration
    - dash_config_info: DASH configuration information dictionary
    - asic_db_checker: Fixture to verify ASIC DB entries
    - acl_default_rule: Default ACL rule configuration
    - skip_underlay_route: Auto-used fixture to skip underlay route tests

Dependencies:
    - constants: DASH test constants (LOCAL_PTF_INTF, REMOTE_PTF_INTF)
    - tests.common.plugins.allure_wrapper: Allure reporting with test steps
    - gnmi_utils: gNMI utilities for configuration application
    - dash_utils: DASH utility functions (render_template_to_host)
    - packets: Packet generation utilities (outbound_vnet_packets)
    - tests.common.utilities: Utility functions (wait_until)
    - tests.common.helpers.assertions: Assertion helpers (pytest_assert)

Notes:
    - ENI admin state configured via dash_set_eni_admin_state.j2 template
    - ASIC_DB key pattern: *ENI:oid*
    - ASIC_DB attribute: SAI_ENI_ATTR_ADMIN_STATE
    - Admin state values: "true" (enabled), "false" (disabled)
    - State verification uses wait_until with 10s timeout, 2s interval
    - Allure steps provide detailed test phase reporting:
      1. Verify traffic when ENI enabled
      2. Disable ENI
      3. Check ASIC_DB confirms disabled state
      4. Verify traffic dropped
      5. Enable ENI
      6. Check ASIC_DB confirms enabled state
      7. Verify traffic forwarded
    - Underlay route scenarios skipped (unnecessary for ENI state control)

Git History (last 1 commit):
    5db0d1e65 Add a new test to cover the scenario of disable/enable ENI (#12977)
"""

import logging
import pytest
import ptf.testutils as testutils
import packets

from constants import LOCAL_PTF_INTF, REMOTE_PTF_INTF
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from gnmi_utils import apply_gnmi_file
from tests.common.dash_utils import render_template_to_host
from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('dpu')
]


@pytest.fixture(autouse=True)
def skip_underlay_route(request):
    if 'with-underlay-route' in request.node.name:
        pytest.skip('Skip the test with param "with-underlay-route", '
                    'it is unnecessary to cover all underlay route scenarios.')


def test_dash_disable_enable_eni(ptfadapter, localhost, duthost, ptfhost, apply_vnet_configs,
                                 dash_config_info, asic_db_checker, acl_default_rule):
    """
    The test is to verify that after the ENI is disabled, the corresponding traffic should be dropped by the DPU.
    """
    asic_db_checker(["SAI_OBJECT_TYPE_VNET", "SAI_OBJECT_TYPE_ENI"])
    with allure.step("Verify the dash traffic when ENI is enabled"):
        _, vxlan_packet, expected_packet = packets.outbound_vnet_packets(dash_config_info)
        testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
        testutils.verify_packets_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])

    def _set_eni_admin_state(state):
        eni_set_state_config = "dash_set_eni_admin_state"
        template_name = f"{eni_set_state_config}.j2"
        dest_path = f"/tmp/{eni_set_state_config}.json"
        render_template_to_host(template_name, duthost, dest_path, dash_config_info, eni_admin_state=state)
        apply_gnmi_file(localhost, duthost, ptfhost, dest_path)

    def _check_eni_admin_state(state):
        asic_db_eni_state = duthost.shell(
            f"redis-cli -n 1 hget {asic_db_eni_key} SAI_ENI_ATTR_ADMIN_STATE")["stdout"]
        return asic_db_eni_state == state

    with allure.step("Disabled the ENI"):
        _set_eni_admin_state("disabled")

    with allure.step("Check ASIC db to confirm the ENI is disabled"):
        asic_db_eni_key = duthost.shell("redis-cli -n 1 keys *ENI:oid*")["stdout"]
        pytest_assert(wait_until(10, 2, 0, _check_eni_admin_state, "false"),
                      "The ENI admin state in ASIC_DB is still true")

    with allure.step("Verify the dash traffic is dropped after ENI is disabled"):
        testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
        testutils.verify_no_packet_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])

    with allure.step("Enable the ENI"):
        _set_eni_admin_state("enabled")

    with allure.step("Check ASIC db to confirm the ENI is enabled"):
        asic_db_eni_key = duthost.shell("redis-cli -n 1 keys *ENI:oid*")["stdout"]
        pytest_assert(wait_until(10, 2, 0, _check_eni_admin_state, "true"),
                      "The ENI admin state in ASIC_DB is still false")

    with allure.step("Verify the dash traffic is forwarded after ENI is enabled"):
        testutils.send(ptfadapter, dash_config_info[LOCAL_PTF_INTF], vxlan_packet, 1)
        testutils.verify_packets_any(ptfadapter, expected_packet, ports=dash_config_info[REMOTE_PTF_INTF])
