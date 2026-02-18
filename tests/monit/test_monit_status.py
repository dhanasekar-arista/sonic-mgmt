"""
=============================================================================
Module: monit
File: test_monit_status.py
=============================================================================

Description:
    This test validates the Monit service running status and its alerting
    message format. Monit is used in older SONiC releases (201811, 201911)
    to monitor critical processes. Tests verify Monit is operational and
    can correctly detect and report process failures.

Test Intent:
    - test_monit_status: Verifies that the Monit service is running and
      configured correctly on the DUT. Waits up to 320 seconds (accounting
      for Monit's 300s start delay) to confirm Monit status command succeeds.
    - test_monit_reporting_message: Validates the format of Monit's alerting
      messages when a critical process (lldpmgrd) is stopped. Verifies Monit
      detects the stopped process and reports it correctly. Only runs on
      201811 and 201911 releases (Supervisord replaced Monit in 202012+).

Topology:
    any topology, including t1-multi-asic

Fixtures Used:
    - stop_and_start_lldpmgrd: Stops lldpmgrd process in a random LLDP
      container at setup and restarts it at teardown. For multi-ASIC, randomly
      selects lldp0 or lldp1 container.
    - duthosts: Provides list of DUT hosts for testing
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one random frontend
      DUT per hardware SKU

Dependencies:
    - tests.common.utilities: For wait_until polling functionality
    - tests.common.helpers.assertions: For pytest assertions and requirements
    - tests.common.helpers.monit: For checking Monit container logging

Notes:
    - Disables loganalyzer for all tests in this module
    - Monit has a 300-second start delay, so test waits up to 320 seconds
    - test_monit_reporting_message only runs on 201811 and 201911 releases
    - test_monit_reporting_message skipped for 202012+ (Supervisord replaced Monit)
    - Expected Monit message format for single ASIC: "'/usr/bin/lldpmgrd' is
      not running in host"
    - Expected Monit message format for multi-ASIC: "'/usr/bin/lldpmgrd' is
      not running in host and in namespace asic0"
    - Waits up to 180 seconds for Monit to detect process failure and log message
    - Also checks for expected container logging format
=============================================================================
"""
import logging

import pytest
import random

from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from tests.common.helpers.assertions import pytest_require
from tests.common.helpers.monit import check_monit_expected_container_logging

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any', 't1-multi-asic'),
    pytest.mark.disable_loganalyzer
]


@pytest.fixture
def stop_and_start_lldpmgrd(duthosts, enum_rand_one_per_hwsku_frontend_hostname):
    """Stops `lldpmgrd` process at setup stage and restarts it at teardwon.

    Args:
        duthosts: The fixture returns list of DuTs.
        enum_rand_one_per_hwsku_frontend_hostname: The fixture randomly pick up
        a frontend DuT from testbed.

    Returns:
        None.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]

    if duthost.is_multi_asic:
        process = random.choice(["lldp0", "lldp1"])
    else:
        process = "lldp"

    logger.info("Stopping 'lldpmgrd' process in {} container ...".format(process))
    stop_command_result = duthost.command("docker exec {} supervisorctl stop lldpmgrd".format(process))
    exit_code = stop_command_result["rc"]
    pytest_assert(exit_code == 0, "Failed to stop 'lldpmgrd' process in {} container!".format(process))
    logger.info("'lldpmgrd' process in {} container is stopped.".format(process))

    yield

    logger.info("Starting 'lldpmgrd' process in {} container ...".format(process))
    start_command_result = duthost.command("docker exec {} supervisorctl start lldpmgrd".format(process))
    exit_code = start_command_result["rc"]
    pytest_assert(exit_code == 0, "Failed to start 'lldpmgrd' process in {} container!".format(process))
    logger.info("'lldpmgrd' process in {} container is started.".format(process))


def check_monit_last_output(duthost):
    """Checks whether alerting message appears as output of command 'monit status' if
    process `lldpmgrd` was stopped.

    Args:
        duthost: An AnsibleHost object of DuT.

    Returns:
        None.
    """
    monit_status_result = duthost.shell("sudo monit status 'lldp|lldpmgrd'", module_ignore_errors=True)
    exit_code = monit_status_result["rc"]
    pytest_assert(exit_code == 0, "Failed to get Monit status of process 'lldpmgrd'!")

    indices = [i for i, s in enumerate(monit_status_result["stdout_lines"]) if 'last output' in s]
    if len(indices) > 0:
        monit_last_output = monit_status_result["stdout_lines"][indices[0]]
        if duthost.is_multi_asic:
            return "/usr/bin/lldpmgrd' is not running in host and in namespace asic0" in monit_last_output
        else:
            return "/usr/bin/lldpmgrd' is not running in host" in monit_last_output
    else:
        return False


def test_monit_status(duthosts, enum_rand_one_per_hwsku_frontend_hostname):
    """Checks whether the Monit service was running or not.

    Args:
        duthosts: The fixture returns list of DuTs.
        enum_rand_one_per_hwsku_frontend_hostname: The fixture randomly picks up
        a frontend DuT from testbed.

    Returns:
        None.
    """
    logger.info("Checking the running status of Monit ...")

    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]

    def _monit_status():
        monit_status_result = duthost.shell("sudo monit status", module_ignore_errors=True)
        return monit_status_result["rc"] == 0
    # Monit is configured with start delay = 300s, hence we wait up to 320s here
    pytest_assert(wait_until(320, 20, 0, _monit_status),
                  "Monit is either not running or not configured correctly")

    logger.info("Checking the running status of Monit was done!")


def test_monit_reporting_message(duthosts, enum_rand_one_per_hwsku_frontend_hostname, stop_and_start_lldpmgrd):
    """Checks whether the format of alerting message from Monit is correct or not.
       202012 and newer image version will be skipped for testing since Supervisord
       replaced Monit to do the monitoring critical processes.

    Args:
        duthosts: The fixture returns list of DuTs.
        enum_rand_one_per_hwsku_frontend_hostname: The fixture randomly pick up
        a frontend DuT from testbed.
        disable_lldp: The fixture function stops `lldpmgrd` process before testing
        and restarts `lldpmgrd` process at teardown.

    Returns:
        None.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]

    pytest_require("201811" in duthost.os_version or "201911" in duthost.os_version,
                   "Test is not supported for 202012 and newer image versions!")

    logger.info("Checking the format of Monit alerting message ...")

    pytest_assert(wait_until(180, 60, 0, check_monit_last_output, duthost),
                  "Expected Monit reporting message not found")
    wait_until(180, 60, 0, check_monit_expected_container_logging, duthost)
    logger.info("Checking the format of Monit alerting message was done!")
