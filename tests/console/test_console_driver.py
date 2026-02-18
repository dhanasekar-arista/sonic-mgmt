"""
=============================================================================
Module: console
File: test_console_driver.py
=============================================================================

Description:
    This test validates the proper installation and functionality of console
    driver components on the DUT. It verifies that virtual TTY devices are
    created correctly by the console driver for all configured console lines.
    The test ensures the console switch hardware infrastructure is properly
    initialized.

Test Intent:
    - test_console_driver: Validates that virtual TTY devices (ttyUSB0-N) are
      created by the console driver for all configured console lines, ensuring
      proper driver installation and device enumeration

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
    - Test verifies presence of /dev/ttyUSB* devices matching console line count
    - Console driver must be properly loaded before test execution
    - Test requires console switch feature to be enabled on DUT
    - Virtual TTY device numbering starts from 0 and matches console line indices
=============================================================================
"""

import pytest

from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.topology('c0', 'c0-lo')
]


def test_console_driver(duthost, tbinfo, setup_c0):
    """
    Test console driver are well installed.
    Verify ttyUSB(0-47) are presented in DUT
    Both c0 and c0-lo have 48 console lines
    """
    topo_console_intfs = tbinfo["topo"]["properties"]["topology"]["console_interfaces"]

    ls_out = duthost.shell('ls {}*'.format(duthost._get_serial_device_prefix()), module_ignore_errors=True)['stdout']
    num_ttys = len(ls_out.split())
    pytest_assert(num_ttys > 0, "No virtual tty devices been created by console driver")
    pytest_assert(num_ttys >= len(topo_console_intfs),
                  "Number of virtual tty devices [{}] is less than expected [{}]"
                  .format(num_ttys, len(topo_console_intfs)))
