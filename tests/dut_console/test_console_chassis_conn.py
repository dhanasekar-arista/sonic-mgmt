"""
=============================================================================
Module: dut_console
File: test_console_chassis_conn.py
=============================================================================

Description:
    Test suite for validating console connectivity to line cards in T2 chassis systems.
    This module tests that each line card can be accessed via serial console from the
    supervisor card, verifying proper serial port connections and console configuration
    in modular chassis deployments.

Test Intent:
    - test_console_availability_serial_ports: Verify console access to all line cards via serial ports from supervisor card

Topology:
    - t2: Test is only for T2 chassis topology

Fixtures Used:
    - duthost: DUT host object (supervisor card)
    - duthosts: All DUT hosts in the testbed
    - enum_supervisor_dut_hostname: Supervisor DUT hostname
    - creds: Credentials for device login

Dependencies:
    - pexpect for console interaction and automation
    - picocom for serial console access (/dev/ttySCD<N>)
    - SSH access to supervisor card
    - Serial connections from supervisor to line cards
    - console_helper module for line card detection

Notes:
    - Test is marked with pytest.mark.topology("t2") - T2 chassis only
    - Test connects from supervisor to each line card via serial console
    - Serial device naming: /dev/ttySCD<N> for Arista platforms
    - Login timeout: 20 seconds for initial prompt, 10 seconds for password
    - Test validates SONiC banner: "Software for Open Networking in the Cloud"
    - get_target_lines returns list of serial port numbers for connected line cards
    - Console access command: sudo /usr/bin/picocom /dev/ttySCD<N>
    - Exit sequence: Ctrl+A, then Ctrl+X to exit picocom
    - Test ensures all line cards are accessible via console
    - Failure indicates serial port misconfiguration or line card issues

=============================================================================
"""

import pexpect
import pytest
import time

from tests.common.helpers.assertions import pytest_assert
from tests.common.helpers.console_helper import get_target_lines, handle_pexpect_exceptions

pytestmark = [
    pytest.mark.topology("t2")  # Test is only for T2 Chassis
]


def test_console_availability_serial_ports(duthost, duthosts, creds, enum_supervisor_dut_hostname):

    duthost = duthosts[enum_supervisor_dut_hostname]
    dutip = duthost.host.options['inventory_manager'].get_host(duthost.hostname).vars['ansible_host']
    dutuser, dutpass = creds['sonicadmin_user'], creds['sonicadmin_password']

    target_lines = get_target_lines(duthost)  # List of Serial port numbers connected from supervisor to linecards

    for target_line in target_lines:
        if 'arista' in duthost.facts['hwsku'].lower():
            console_command = f"sudo /usr/bin/picocom /dev/ttySCD{target_line}"
            try:
                client = pexpect.spawn('ssh {}@{} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
                                       .format(dutuser, dutip))
                client.expect('[Pp]assword:')
                client.sendline(dutpass)
                client.sendline(console_command)
                time.sleep(5)
                client.sendline('\n')
                client.expect(['login:'], timeout=20)
                client.sendline(dutuser)
                client.expect(['[Pp]assword:'], timeout=10)
                client.sendline(dutpass)

                i = client.expect([r'.*Software\s+for\s+Open\s+Networking\s+in\s+the\s+Cloud.*',
                                   'Login incorrect'], timeout=100)
                pytest_assert(i == 0,
                              f"Failed to connect to line card {target_line} "
                              "on Arista device. Please check credentials.")

                client.sendline('exit')
                time.sleep(2)
                client.sendcontrol('a')
                time.sleep(2)
                client.sendcontrol('x')
            except Exception as e:
                handle_pexpect_exceptions(target_line)(e)

        elif 'cisco' in duthost.facts['hwsku'].lower():
            console_command = f"sudo /opt/cisco/bin/rconsole.py -s {target_line}"
            try:
                client = pexpect.spawn('ssh {}@{} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
                                       .format(dutuser, dutip))
                client.expect('[Pp]assword:')
                client.sendline(dutpass)
                time.sleep(10)
                client.sendline(console_command)
                time.sleep(10)
                client.sendline(dutuser)
                client.expect(['[Pp]assword:'], timeout=10)
                time.sleep(10)
                client.sendline(dutpass)
                time.sleep(10)

                i = client.expect([r'.*Software\s+for\s+Open\s+Networking\s+in\s+the\s+Cloud.*',
                                   'Login incorrect'], timeout=100)
                pytest_assert(i == 0,
                              f"Failed to connect to line card {target_line} on Cisco device.Please check credentials.")

                client.sendline('exit')
                time.sleep(2)
                client.sendcontrol('\\')
                time.sleep(2)
                client.sendline('quit')

            except Exception as e:
                handle_pexpect_exceptions(target_line)(e)

        else:
            pytest.skip("Skipping test because test is not supported on this hwsku.")
