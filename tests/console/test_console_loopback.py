"""
=============================================================================
Module: console
File: test_console_loopback.py
=============================================================================

Description:
    This test validates bidirectional data transfer capabilities through the console
    switch using loopback configurations. It tests both single-line echo (data sent
    and received on same line) and cross-line ping-pong (data sent between paired
    console lines) scenarios to verify proper serial data transmission, timing, and
    routing through the console switch hardware.

Test Intent:
    - test_console_loopback_echo: Validates single-line loopback by sending random
      64-byte strings to console lines (1-16) and verifying the data is echoed back
      within timing constraints based on configured baud rate
    - test_console_loopback_pingpong: Validates cross-line communication by establishing
      sessions on paired console lines and verifying bidirectional message exchange
      ('ping'/'pong') between physically looped line pairs

Topology:
    any

Fixtures Used:
    - duthost: DUT host fixture for executing commands on the device under test
    - creds: Credentials fixture providing sonicadmin username and password
    - skip_if_os_not_support: Auto-fixture that skips tests on unsupported OS versions
      (201803, 201807, 201811, 201911)
    - skip_if_console_feature_disabled: Auto-fixture that skips tests when console
      switch feature is disabled
    - console_facts: Provides console configuration and state information from DUT

Dependencies:
    - pexpect: For interactive SSH session control (via console_helper)
    - tests.common.helpers.console_helper: assert_expect_text, create_ssh_client,
      ensure_console_session_up helper functions
    - string, random: For generating random test data
    - conftest.py: Module-level fixtures for OS version and feature checks

Notes:
    - Echo test parametrized for lines 1-16, tests skipped if line not configured
    - Ping-pong test uses specific line pairs: (17,19), (18,20), (21,27), (22,28),
      (23,25), (24,26), (29,35), (30,36), (31,33), (32,34)
    - Timeout calculated dynamically: (packet_size * 8 * delay_factor) / baud_rate
    - Default packet size is 64 bytes with 2.0x delay factor for timing margin
    - Physical loopback cables must connect paired console lines for ping-pong tests
    - Tests verify data integrity and timing characteristics of serial communication
=============================================================================
"""

import pytest
import random
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until
from tests.common.helpers.console_helper import assert_expect_text, create_ssh_client, ensure_console_session_up
from tests.common.helpers.console_helper import generate_random_string, check_target_line_status

pytestmark = [
    pytest.mark.topology('c0', 'c0-lo')
]


console_lines = list(map(str, range(1, 49)))


@pytest.mark.parametrize("target_line", console_lines)
@pytest.mark.parametrize("baud_rate", ["9600", "115200"])
def test_console_loopback_echo(setup_c0, creds, target_line, baud_rate, cleanup_modules):
    """
    Test data transfer is working as expect.
    Verify data can go out through the console switch and come back through the console switch
    """
    duthost, console_fanout = setup_c0
    duthost.command("config console baud {} {}".format(target_line, baud_rate))
    duthost.shell("show line | awk '$1 == \"{}\" {{ print $2 }}' | grep {}".format(target_line, baud_rate))
    # c0-lo
    if duthost.hostname == console_fanout.hostname:
        duthost.command("config console flow_control enable {}".format(target_line))
        delay_factor = 1.6
    # c0
    else:
        duthost.command("config console flow_control disable {}".format(target_line))
        console_fanout.command("config console flow_control disable {}".format(target_line))
        console_fanout.set_loopback(target_line, baud_rate, False)
        delay_factor = 3.2

    dutip = duthost.host.options['inventory_manager'].get_host(duthost.hostname).vars['ansible_host']
    dutuser = creds['sonicadmin_user']
    dutpass = creds['sonicadmin_password']

    packet_size = 64

    # Estimate a reasonable data transfer time based on configured baud rate
    timeout_sec = (packet_size * 10) * delay_factor / int(baud_rate)
    ressh_user = "{}:{}".format(dutuser, target_line)

    try:
        client = create_ssh_client(dutip, ressh_user, dutpass)
        ensure_console_session_up(client, target_line)

        # Generate a random strings to send
        text = generate_random_string(packet_size)
        client.sendline(text)
        assert_expect_text(client, text, target_line, timeout_sec)

    except Exception as e:
        pytest.fail("Not able to communicate DUT via reverse SSH: {}".format(e))
    finally:
        client.sendcontrol('a')
        client.sendcontrol('x')
        pytest_assert(
            wait_until(10, 1, 0, check_target_line_status, duthost, target_line, "IDLE"),
            "Target line {} is busy after exited reverse SSH session".format(target_line))

    if duthost.hostname != console_fanout.hostname:
        console_fanout.unset_loopback(target_line)


@pytest.mark.topology('c0')
@pytest.mark.parametrize("src_line,dst_line", [random.sample(console_lines, 2) for _ in range(4)])
@pytest.mark.parametrize("baud_rate", ["9600", "115200"])
def test_console_loopback_pingpong(setup_c0, creds, src_line, dst_line, baud_rate, cleanup_modules):
    """
    Test data transfer is working as expect.
    Verify data can go out through the console switch and come back through the console switch
    """
    duthost, console_fanout = setup_c0
    duthost.command("config console baud {} {}".format(src_line, baud_rate))
    duthost.command("config console baud {} {}".format(dst_line, baud_rate))
    duthost.command("config console flow_control disable {}".format(src_line))
    duthost.command("config console flow_control disable {}".format(dst_line))
    console_fanout.bridge(src_line, dst_line, baud_rate, False)

    dutip = duthost.host.options['inventory_manager'].get_host(duthost.hostname).vars['ansible_host']
    dutuser = creds['sonicadmin_user']
    dutpass = creds['sonicadmin_password']

    try:
        sender = create_ssh_client(dutip, "{}:{}".format(dutuser, src_line), dutpass)
        receiver = create_ssh_client(dutip, "{}:{}".format(dutuser, dst_line), dutpass)

        ensure_console_session_up(sender, src_line)
        ensure_console_session_up(receiver, dst_line)

        sender.sendline('ping')
        assert_expect_text(receiver, 'ping', dst_line, timeout_sec=1)
        receiver.sendline('pong')
        assert_expect_text(sender, 'pong', src_line, timeout_sec=1)

    except Exception:
        pytest.fail("Not able to communicate DUT via reverse SSH")
    finally:
        sender.sendcontrol('a')
        sender.sendcontrol('x')
        receiver.sendcontrol('a')
        receiver.sendcontrol('x')
        pytest_assert(
            wait_until(10, 1, 0, check_target_line_status, duthost, src_line, "IDLE"),
            "Target line {} of dut is busy after exited reverse SSH session".format(src_line))
        pytest_assert(
            wait_until(10, 1, 0, check_target_line_status, console_fanout, dst_line, "IDLE"),
            "Target line {} of fanout is busy after exited reverse SSH session".format(dst_line))

    console_fanout.unbridge(src_line, dst_line)
