"""
=============================================================================
Module: dut_console
File: test_escape_character.py
=============================================================================

Description:
    Test suite for validating console escape character (Ctrl+C) functionality. This module
    tests that interrupt signals can be sent through the console to terminate running
    commands, verifying proper terminal control character handling over console connections.

Test Intent:
    - test_console_escape: Verify Ctrl+C escape character interrupts running ping command and terminates it early

Topology:
    - any: Test works on any topology (t0, t1, t2, m0, mx, etc.)

Fixtures Used:
    - duthost_console: Console connection to DUT

Dependencies:
    - Console connection supporting terminal control characters
    - ping command for long-running process simulation
    - Pattern matching for command output parsing

Notes:
    - Test is marked with pytest.mark.topology('any')
    - Test sends ping to localhost (127.0.0.1) for 100 packets
    - Ctrl+C (0x03) sent after 10 packets to interrupt ping
    - Expected behavior: Ping terminates after 10 packets instead of 100
    - Tests raw terminal control character transmission (write_channel)
    - Verifies console can send ASCII control characters correctly
    - Pattern match: "icmp_seq=10" to wait for 10th packet
    - Final pattern: "10 packets transmitted" to verify early termination

=============================================================================
"""

import logging
import pytest


TOTAL_PACKETS = 100
packet_number = 10
logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]


def test_console_escape(duthost_console):
    duthost_console.send_command("ping 127.0.0.1 -c {} -i 1".format(TOTAL_PACKETS),
                                 expect_string=r"icmp_seq={}".format(packet_number))
    # Send interrupt character directly
    duthost_console.write_channel("\x03")
    # Matching the expected output content
    duthost_console.read_until_pattern(pattern=r"{} packets transmitted".format(packet_number))
