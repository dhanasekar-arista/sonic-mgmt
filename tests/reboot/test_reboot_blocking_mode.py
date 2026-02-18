"""
=============================================================================
Module: reboot
File: test_reboot_blocking_mode.py
=============================================================================

Description:
    This test validates the SONiC reboot blocking mode functionality which
    allows the reboot command to wait for system readiness before initiating
    reboot. Tests both CLI-based blocking mode and config file-based blocking
    mode configurations.

Test Intent:
    - test_non_blocking_mode: Verifies default non-blocking reboot behavior
      where the reboot command returns immediately after execution without
      waiting for system state checks
    - test_blocking_mode: Validates blocking mode enabled via CLI flag (-b)
      ensures the reboot command blocks and displays progress dots, not
      returning until system is ready or timeout occurs
    - test_timeout_for_blocking_mode: Tests blocking mode configured via
      /etc/sonic/reboot.conf with blocking_mode_timeout=0, verifying command
      returns immediately when timeout is zero

Topology:
    any topology

Fixtures Used:
    - setup_teardown: Function-scoped autouse fixture that mocks systemctl
      reboot to prevent actual reboots, disables watchdog, and performs
      cleanup by restoring original reboot script and rebooting DUT safely

Dependencies:
    - tests.common.reboot: Safe reboot functionality
    - tests.common.helpers.assertions: Assertion utilities

Notes:
    - Skips test if platform_reboot is enabled on the device
    - Mocks /sbin/reboot to prevent actual system reboot during test
    - Backs up original /sbin/reboot to /sbin/reboot.bak before mocking
    - Disables watchdog by replacing /usr/local/bin/watchdogutil references
    - Uses 90-second timeout for command execution
    - Blocking mode config file format: blocking_mode=true, show_timer=true
    - Validates progress dots appear in blocking mode output
    - Restores all mocked files and performs real reboot in teardown
    - Test expects "ExpectedFinished" in non-blocking output
    - Test expects absence of "UnexpectedFinished" in blocking output
=============================================================================
"""
import pytest
import re
from tests.common.reboot import reboot
from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology('any'),
]

COMMAND_TIMEOUT = 90  # seconds


def check_if_platform_reboot_enabled(duthost) -> bool:
    platform = get_command_result(duthost, "sonic-cfggen -H -v DEVICE_METADATA.localhost.platform")
    return check_if_dut_file_exist(duthost, "/usr/share/sonic/device/{}/platform_reboot".format(platform))


def mock_systemctl_reboot(duthost):
    if not check_if_dut_file_exist(duthost, "/sbin/reboot.bak"):
        # Check exist to avoid override original reboot file.
        execute_command(duthost, "sudo mv /sbin/reboot /sbin/reboot.bak")
    execute_command(duthost, "sudo echo \"\" > /sbin/reboot")
    execute_command(duthost, "sudo chmod +x /sbin/reboot")
    execute_command_ignore_error(duthost, "sudo /usr/local/bin/watchdogutil disarm")

    # Disable watch dog to avoid reboot too early.
    execute_command(
        duthost,
        "sudo sed -i 's#/usr/local/bin/watchdogutil#/usr/local/bin/disabled_watchdogutil#g' /usr/local/bin/reboot")


def restore_systemctl_reboot_and_reboot(duthost, localhost):
    if not check_if_dut_file_exist(duthost, "/sbin/reboot.bak"):
        return
    execute_command(duthost, "sudo rm /sbin/reboot")
    execute_command(duthost, "sudo mv /sbin/reboot.bak /sbin/reboot")
    execute_command(
        duthost,
        "sudo sed -i 's#/usr/local/bin/disabled_watchdogutil#/usr/local/bin/watchdogutil#g' /usr/local/bin/reboot")
    reboot(duthost, localhost, safe_reboot=True)


def mock_reboot_config_file(duthost):
    if (
        check_if_dut_file_exist(duthost, "/etc/sonic/reboot.conf")
        and not check_if_dut_file_exist(duthost, "/etc/sonic/reboot.conf.bak")
    ):
        execute_command(duthost, "sudo mv /etc/sonic/reboot.conf /etc/sonic/reboot.conf.bak")
    execute_command(
        duthost,
        "echo -e \"blocking_mode=true\\nshow_timer=true\" > /etc/sonic/reboot.conf")


def mock_reboot_config_file_with_0_timeout(duthost):
    if (
        check_if_dut_file_exist(duthost, "/etc/sonic/reboot.conf")
        and not check_if_dut_file_exist(duthost, "/etc/sonic/reboot.conf.bak")
    ):
        execute_command(duthost, "sudo mv /etc/sonic/reboot.conf /etc/sonic/reboot.conf.bak")
    execute_command(
        duthost,
        "echo -e \"blocking_mode=true\\nblocking_mode_timeout=0\\nshow_timer=true\" > /etc/sonic/reboot.conf")


def restore_reboot_config_file(duthost):
    execute_command(duthost, "sudo rm /etc/sonic/reboot.conf")
    if check_if_dut_file_exist(duthost, "/etc/sonic/reboot.conf.bak"):
        execute_command(duthost, "sudo mv /etc/sonic/reboot.conf.bak /etc/sonic/reboot.conf")


def execute_command(duthost, cmd):
    result = duthost.shell(cmd)
    pytest_assert(result["rc"] == 0, "Unexpected rc: {}".format(result["rc"]))


def execute_command_ignore_error(duthost, cmd):
    duthost.shell(cmd, module_ignore_errors=True)


def get_command_result(duthost, cmd):
    result = duthost.shell(cmd, module_ignore_errors=True)
    return result["stdout"]


def check_if_dut_file_exist(duthost, filepath) -> bool:
    result = duthost.shell(f"test -f {filepath} && echo true || echo false", module_ignore_errors=True)
    return "true" in result["stdout"]


class TestRebootBlockingModeCLI:
    @pytest.fixture(autouse=True, scope="function")
    def setup_teardown(
        self,
        duthosts,
        enum_rand_one_per_hwsku_hostname,
        localhost
    ):
        duthost = duthosts[enum_rand_one_per_hwsku_hostname]
        if check_if_platform_reboot_enabled(duthost):
            pytest.skip("Skip test because platform reboot is enabled.")

        mock_systemctl_reboot(duthost)
        yield
        restore_systemctl_reboot_and_reboot(duthost, localhost)

    def test_non_blocking_mode(
        self,
        duthosts,
        enum_rand_one_per_hwsku_hostname
    ):
        duthost = duthosts[enum_rand_one_per_hwsku_hostname]
        result = get_command_result(
            duthost,
            f"sudo timeout {COMMAND_TIMEOUT}s bash -c 'sudo reboot; echo \"ExpectedFinished\"'")
        pytest_assert("ExpectedFinished" in result, "Reboot didn't exited as expected.")

    def test_blocking_mode(
        self,
        duthosts,
        enum_rand_one_per_hwsku_hostname
    ):
        duthost = duthosts[enum_rand_one_per_hwsku_hostname]
        result = get_command_result(
            duthost,
            f"sudo timeout {COMMAND_TIMEOUT}s bash -c 'sudo reboot -b -v; echo \"UnexpectedFinished\"'")
        pytest_assert("UnexpectedFinished" not in result, "Reboot script didn't blocked as expected.")
        pattern = r".*\n[.]+$"
        pytest_assert(re.search(pattern, result), "Cannot find dots as expected in output: {}".format(result))


class TestRebootBlockingModeConfigFile:
    @pytest.fixture(autouse=True, scope="function")
    def setup_teardown(
        self,
        duthosts,
        enum_rand_one_per_hwsku_hostname,
        localhost
    ):
        duthost = duthosts[enum_rand_one_per_hwsku_hostname]
        if check_if_platform_reboot_enabled(duthost):
            pytest.skip("Skip test because platform reboot is enabled.")

        mock_systemctl_reboot(duthost)
        yield

        restore_reboot_config_file(duthost)
        restore_systemctl_reboot_and_reboot(duthost, localhost)

    def test_timeout_for_blocking_mode(
        self,
        duthosts,
        enum_rand_one_per_hwsku_hostname
    ):
        duthost = duthosts[enum_rand_one_per_hwsku_hostname]
        mock_reboot_config_file_with_0_timeout(duthost)
        result = get_command_result(
            duthost,
            f"sudo timeout {COMMAND_TIMEOUT}s bash -c 'sudo reboot; echo \"ExpectedFinished\"'")
        pytest_assert("ExpectedFinished" in result, "Reboot didn't exited as expected.")
