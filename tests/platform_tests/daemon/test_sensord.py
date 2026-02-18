"""
=============================================================================
Module: platform_tests
File: test_sensord.py
=============================================================================

Description:
    Tests for lm-sensors daemon (sensord) in the PMON container. Validates daemon
    lifecycle management including start, stop, restart, and signal handling.

Test Intent:
    - test_sensord_running_status: Verify sensord is running after PMON start
    - test_sensord_stop_and_start_status: Validate manual stop/start operations
    - test_sensord_stop_and_restart_status: Test stop followed by restart
    - test_kill_sensord_sig_term: Verify sensord restarts after SIGTERM
    - test_kill_sensord_sig_kill: Validate sensord restarts after SIGKILL
    - test_kill_sensord_sig_hup: Test sensord handles SIGHUP gracefully

Topology:
    Any topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - rand_one_dut_hostname: Selects one random DUT
    - check_sensord_supported: Module-scoped fixture validating sensord support
    - sensord_start_and_get_pid: Function-scoped fixture ensuring sensord running

Dependencies:
    - lm-sensors supervisor task in pmon container
    - /etc/sensors.d/sensors.conf configuration file
    - check_sensord_status and start_pmon_sensord_task helpers

Notes:
    - Test skips if sensors.conf not present for SKU
    - Test skips if lm-sensors not supported on platform
    - Uses supervisorctl for daemon lifecycle control
    - Validates PID changes after restart operations
    - Signal constants: SIG_KILL (-9), SIG_TERM (-15), SIG_HUP (-1)
    - Sensord monitors hardware sensors (temperature, voltage, fan speeds)
    - Daemon should auto-restart after kill signals
    - Loganalyzer disabled (expected error logs during daemon restarts)
    - Sanity check skipped for this test suite
=============================================================================
"""
import logging
import time

import pytest

from tests.platform_tests.test_platform_info import check_sensord_status, start_pmon_sensord_task

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer
]

SIG_KILL = "-9"
SIG_TERM = "-15"
SIG_HUP = "-1"


@pytest.fixture(scope="module")
def check_sensord_supported(duthosts, rand_one_dut_hostname):
    """
    @summary: Check that sensord is enabled / supported by the SKU
    """
    duthost = duthosts[rand_one_dut_hostname]

    cmd = "docker exec pmon ls /etc/sensors.d/sensors.conf"
    no_sensors_config = duthost.shell(cmd, module_ignore_errors=True)['failed']
    if no_sensors_config:
        pytest.skip(f"No sensors.conf for this SKU {duthost.facts['platform']}")

    cmd = 'docker exec pmon supervisorctl status lm-sensors 2>&1 | grep "no such process" > /dev/null'
    no_sensors_supported = duthost.shell(cmd, module_ignore_errors=True)['rc'] == 0
    if no_sensors_supported:
        pytest.skip(f"lm-sensors not supported for this SKU {duthost.facts['platform']}")


@pytest.fixture(scope="function")
def sensord_start_and_get_pid(duthosts, rand_one_dut_hostname, check_sensord_supported):
    """
    @summary: Ensure sensord is running, and provide the PID to the testcase
    """
    duthost = duthosts[rand_one_dut_hostname]

    started, pid = start_pmon_sensord_task(duthost)
    if not started:
        pytest.fail("Failed to start sensord before test")

    yield pid

    started, _ = start_pmon_sensord_task(duthost)
    if not started:
        pytest.fail("Failed to start sensord after test")


def assert_expected_daemon_status(duthost, expected_daemon_status, expected_pid=None):
    daemon_status, pid = check_sensord_status(duthost)
    assert daemon_status == expected_daemon_status
    if expected_pid:
        assert expected_pid == pid


def test_pmon_sensord_sigterm(sensord_start_and_get_pid, duthosts, rand_one_dut_hostname):
    """
    @summary: Assert that sensord stops after sigterm
    """
    duthost = duthosts[rand_one_dut_hostname]

    sensord_pid = sensord_start_and_get_pid

    duthost.kill_pmon_daemon_pid_w_sig(sensord_pid, SIG_TERM)
    time.sleep(2)

    assert_expected_daemon_status(duthost, False)


def test_pmon_sensord_sigkill(sensord_start_and_get_pid, duthosts, rand_one_dut_hostname):
    """
    @summary: Assert that sensord stops after sigkill
    """
    duthost = duthosts[rand_one_dut_hostname]

    sensord_pid = sensord_start_and_get_pid

    duthost.kill_pmon_daemon_pid_w_sig(sensord_pid, SIG_KILL)
    time.sleep(2)

    assert_expected_daemon_status(duthost, False)


def test_pmon_sensord_sighup(sensord_start_and_get_pid, duthosts, rand_one_dut_hostname):
    """
    @summary: Assert that sensord remains running after receiving a sighup
    """
    duthost = duthosts[rand_one_dut_hostname]

    sensord_pid = sensord_start_and_get_pid

    duthost.kill_pmon_daemon_pid_w_sig(sensord_pid, SIG_HUP)
    time.sleep(2)

    # daemon should still be running with the same pid
    assert_expected_daemon_status(duthost, True, expected_pid=sensord_pid)
