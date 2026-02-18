"""
=============================================================================
Module: platform_tests
File: test_reboot_cause.py
=============================================================================

Description:
    Mellanox-specific test validating reboot cause detection from BIOS and ASIC
    reset sources. Uses RebootCauseMocker to simulate different reboot types and
    verifies determine-reboot-cause service reports correct cause.

Test Intent:
    - test_reboot_cause: Verify reboot cause detection for BIOS and ASIC reset types

Topology:
    Any topology - Mellanox platforms only

Fixtures Used:
    - rand_selected_dut: Randomly selected DUT
    - mocker_factory: Creates RebootCauseMocker for simulating reboot causes

Dependencies:
    - RebootCauseMocker for simulating reset conditions
    - determine-reboot-cause systemd service
    - check_reboot_cause helper function

Notes:
    - Test only runs on Mellanox ASIC platforms
    - Parametrized test covering REBOOT_TYPE_BIOS and REBOOT_TYPE_ASIC
    - Mocks hardware reset registers to simulate reboot causes
    - Restarts determine-reboot-cause service to trigger detection
    - Validates reboot cause matches expected type
    - Allure test reporting integration with step-by-step tracking
    - Does not perform actual system reboot (uses mocking)
=============================================================================
"""
import allure
import logging
import pytest
from tests.common.reboot import REBOOT_TYPE_BIOS, REBOOT_TYPE_ASIC, check_reboot_cause
from tests.common.helpers.sensor_control_test_helper import mocker_factory  # noqa: F401

pytestmark = [
    pytest.mark.asic('mellanox'),
    pytest.mark.topology('any')
]

logger = logging.getLogger(__name__)

mocker = None
REBOOT_CAUSE_TYPES = [REBOOT_TYPE_BIOS, REBOOT_TYPE_ASIC]


@pytest.mark.parametrize("reboot_cause", REBOOT_CAUSE_TYPES)
def test_reboot_cause(rand_selected_dut, mocker_factory, reboot_cause):  # noqa: F811
    """
    Validate reboot cause from cpu/bios/asic
    :param rand_selected_dut: The fixture returns a randomly selected DUT
    :param mocker_factory: The fixture returns a mocker
    :param reboot_cause: The specific reboot cause
    """
    duthost = rand_selected_dut
    with allure.step('Create mocker - RebootCauseMocker'):
        mocker = mocker_factory(duthost, 'RebootCauseMocker')

    with allure.step('Mock reset from {}'.format(reboot_cause)):
        if reboot_cause == REBOOT_TYPE_BIOS:
            mocker.mock_reset_reload_bios()
        elif reboot_cause == REBOOT_TYPE_ASIC:
            mocker.mock_reset_from_asic()

    with allure.step('Restart determine-reboot-cause service'):
        duthost.restart_service('determine-reboot-cause')

    with allure.step('Check Reboot cause is {}'.format(reboot_cause)):
        check_reboot_cause(duthost, reboot_cause)
