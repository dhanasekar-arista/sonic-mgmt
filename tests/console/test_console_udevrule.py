"""
=============================================================================
Module: console
File: test_console_udevrule.py
=============================================================================

Description:
    This test validates the proper functioning of udev rules for console port
    mapping on the DUT. It verifies that console TTY devices are correctly mapped
    to user-friendly device names (C0-N format) through udev rules. This mapping
    provides intuitive console port access for administrators.

Test Intent:
    - test_console_port_mapping: Validates that udev rules create console device
      symlinks (C0-1, C0-2, etc.) for all configured console lines, ensuring
      proper port mapping and device naming conventions

Topology:
    any

Fixtures Used:
    - duthost: DUT host fixture for executing commands on the device under test
    - skip_if_os_not_support: Auto-fixture that skips tests on unsupported OS versions
      (201803, 201807, 201811, 201911)
    - skip_if_console_feature_disabled: Auto-fixture that skips tests when console
      switch feature is disabled
    - console_facts: Provides console configuration and state information from DUT

Dependencies:
    - tests.common.helpers.assertions: pytest_assert for test validation
    - conftest.py: Module-level fixtures for OS version and feature checks

Notes:
    - Test verifies presence of /dev/C0-* devices for all configured console lines
    - Udev rules must be properly installed and applied before test execution
    - Console device naming format is C0-N where N is the line number
    - Test requires console switch feature to be enabled on DUT
=============================================================================
"""
import pytest

from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.topology('any')
]


def test_console_port_mapping(duthost):
    out = duthost.shell('ls /dev/C0-*', module_ignore_errors=True)['stdout']
    ttys = set(out.split())
    pytest_assert(len(ttys) > 0, "No console tty devices been created by udev rule")

    out = list(duthost.console_facts()["ansible_facts"]["console_facts"]["lines"].keys())
    for i in out:
        expected_console_tty = "/dev/C0-{}".format(i)
        pytest_assert(
            expected_console_tty in ttys,
            "Expected console device [{}] not found.".format(expected_console_tty))
