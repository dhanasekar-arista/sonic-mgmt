"""
=============================================================================
Module: console
File: test_console_availability.py
=============================================================================

Description:
    This test validates end-to-end console connectivity in virtual switch (VS)
    environments. It sets up a complete console loopback path using socat to
    create virtual serial connections, then verifies that console access is
    functional through the entire chain (DUT -> KVM host -> virtual device ->
    console line connection).

Test Intent:
    - test_console_availability: Validates full console connectivity by setting up
      socat-based virtual serial devices, configuring console lines with specific
      baud rates, establishing connections via 'connect line' command, and verifying
      successful console session establishment

Topology:
    any (specifically designed for virtual switch environments)

Fixtures Used:
    - duthost: DUT host fixture for executing commands on the device under test
    - creds: Credentials fixture providing sonicadmin username and password
    - skip_if_os_not_support: Auto-fixture that skips tests on unsupported OS versions
      (201803, 201807, 201811, 201911)
    - skip_if_console_feature_disabled: Auto-fixture that skips tests when console
      switch feature is disabled

Dependencies:
    - pexpect: For interactive SSH session control and automation
    - getpass: For retrieving current user information
    - tests.common.helpers.assertions: pytest_assert for test validation
    - socat: External utility for virtual serial port creation (installed during test)
    - conftest.py: Module-level fixtures for OS version and feature checks

Notes:
    - Test is marked for device_type "vs" (virtual switch) only
    - Parametrized to test console lines 1, 2, 3, and 4
    - Automatically installs socat on both DUT and KVM host if not present
    - Uses TCP port mapping: 2000+line_number for forwarding to 7000+line_number-1
    - Console lines are dynamically configured with 9600 baud rate
    - Test verifies "Successful connection" message and login prompt appearance
    - Requires KVM host accessible at 172.17.0.1
    - Cleans up existing socat and picocom processes before test execution
=============================================================================
"""

import getpass
import pexpect
import pytest

from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.topology("any"),
    pytest.mark.device_type("vs")
]


@pytest.mark.parametrize("target_line", ["1", "2", "3", "4"])
def test_console_availability(duthost, creds, target_line, cleanup_modules):
    """
    Test console are well functional.
    Verify console access is available after connecting from DUT
    """
    dutip = duthost.host.options['inventory_manager'].get_host(duthost.hostname).vars['ansible_host']
    dutuser, dutpass = creds['sonicadmin_user'], creds['sonicadmin_password']
    hostip, hostuser = "172.17.0.1", getpass.getuser()

    res = duthost.shell("which socat", module_ignore_errors=True)
    if res["rc"] != 0:
        # install socat to DUT host
        duthost.copy(src="./console/socat", dest="/usr/local/bin/socat", mode=755)

    out = pexpect.run("ssh {}@{} -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null 'which socat'".format(
        hostuser, hostip))
    if not out:
        # install socat to KVM host
        pexpect.run("scp -q {} {}@{}:{}".format("./console/socat", hostuser, hostip, "/usr/local/bin/socat"))

    pytest_assert(duthost.shell("socat -V", module_ignore_errors=True)["rc"] == 0,
                  "Invalid socat installation on DUT host")
    pytest_assert(int(pexpect.run("ssh {}@{} -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                                  "'socat -V > /dev/null 2>&1; echo $?'".format(hostuser, hostip))) == 0,
                  "Invalid socat installation on KVM host")

    out = pexpect.run("ssh {0}@{1} -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                      "'sudo killall -q socat;"
                      "sudo lsof -i:{3} > /dev/null &&"
                      "sudo socat TCP-LISTEN:{2},fork,reuseaddr TCP:127.0.0.1:{3} & echo $?'"
                      .format(hostuser, hostip, 2000 + int(target_line), 7000 + int(target_line) - 1))
    pytest_assert(int(out.strip()) == 0, "Failed to start socat on KVM host")

    try:
        client = pexpect.spawn(
            "ssh {2}@{3} -q -t -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            "'sudo killall -q socat;"
            "sudo killall -q picocom;"
            "sudo socat PTY,link=/dev/ttyUSB{0} TCP:10.250.0.1:{1},forever &"
            "while [ ! -e /dev/ttyUSB{0} ]; do sleep 1; done;"
            "sudo config console del {0} > /dev/null 2>&1;"
            "sudo config console add {0} --baud 9600 --devicename device{0};"
            "sudo connect line {0}'".format(
                target_line, 2000 + int(target_line), dutuser, dutip))
        client.expect('[Pp]assword:')
        client.sendline(dutpass)

        i = client.expect(['Successful connection', 'Cannot connect'], timeout=10)
        pytest_assert(i == 0,
                      "Failed to connect line {}".format(target_line))
        client.expect(['login:', '[:>~$]'], timeout=10)
    except pexpect.exceptions.EOF:
        pytest.fail("EOF reached")
    except pexpect.exceptions.TIMEOUT:
        pytest.fail("Timeout reached")
    except Exception as e:
        pytest.fail("Cannot connect to DUT host via SSH: {}".format(e))
