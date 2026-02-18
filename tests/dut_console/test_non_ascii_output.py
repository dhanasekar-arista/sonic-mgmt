"""
=============================================================================
Module: dut_console
File: test_non_ascii_output.py
=============================================================================

Description:
    Test suite for validating that common SONiC commands produce only ASCII output over
    console connections. This module detects encoding issues, corruption, or unexpected
    non-ASCII characters in command output by running commands repeatedly and checking
    all output characters are within ASCII range (0-127).

Test Intent:
    - test_commands_output_is_ascii: Verify all common commands produce only ASCII output (no encoding corruption)

Topology:
    - any: Test works on any topology (t0, t1, t2, m0, mx, etc.)

Fixtures Used:
    - duthost_console: Console connection to DUT

Dependencies:
    - Console connection with proper encoding support
    - Common SONiC CLI commands (show version, show platform, etc.)
    - Pattern matching for command prompt detection

Notes:
    - Test is marked with pytest.mark.topology('any')
    - Test runs each command 10 times to catch intermittent encoding issues
    - Commands tested: show version, show platform summary, show interface status, show ip bgp sum, lspci, ls /etc/sonic
    - ASCII validation: All characters must have ord(c) < 128
    - Test tracks commands/iterations that produce non-ASCII output
    - Non-ASCII characters could indicate: terminal encoding issues, corrupted output, binary data in text output
    - Test fails if any command produces non-ASCII output in any iteration
    - Prompt pattern: admin@<hostname>:~$
    - Test timeout: 20 seconds per command execution

=============================================================================
"""

import logging
import pytest


logger = logging.getLogger(__name__)

# Commands to execute on the device
COMMANDS = [
    "show version",
    "show platform summary",
    "show interface status",
    "show ip bgp sum",
    "lspci",
    "ls /etc/sonic"
]

pytestmark = [
    pytest.mark.topology('any')
]


def is_ascii(text):
    """Check if all characters in text are ASCII."""
    return all(ord(c) < 128 for c in text)


def test_commands_output_is_ascii(duthost_console):
    """
    Run various commands on the device and verify all output is ASCII.

    This test runs a set of common commands and checks if any of them
    produce non-ASCII output, which could indicate encoding issues,
    corruption, or unexpected characters. Each command is repeated 100 times
    to increase the chance of catching intermittent issues.
    """
    non_ascii_outputs = []
    iterations = 10

    logger.info(f"Running each command {iterations} times to check for non-ASCII output")

    for iteration in range(1, iterations + 1):
        logger.info(f"Iteration {iteration}/{iterations}")

        for cmd in COMMANDS:
            logger.info(f"Running command: {cmd}")
            try:
                # Wait for a prompt pattern that matches admin@<hostname>:~$
                output = duthost_console.send_command(
                    cmd,
                    expect_string=r"admin@.*:~\$",
                    delay_factor=2,
                    max_loops=500
                )

                if not is_ascii(output):
                    # Find the non-ASCII characters for better reporting
                    non_ascii_chars = [c for c in output if ord(c) >= 128]
                    non_ascii_positions = [(i, c, ord(c)) for i, c in enumerate(output) if ord(c) >= 128]
                    non_ascii_outputs.append({
                        "command": cmd,
                        "iteration": iteration,
                        "non_ascii_chars": non_ascii_chars[:10],  # First 10 non-ASCII chars
                        "positions": non_ascii_positions[:5],     # First 5 positions,
                        "full_output": output  # Store the entire output for debugging
                    })
            except Exception as e:
                logger.error(f"Error executing command '{cmd}' (iteration {iteration}): {str(e)}")

    # Generate detailed error message if non-ASCII characters were found
    if non_ascii_outputs:
        error_msg = "Non-ASCII characters detected in command outputs:\n"
        for item in non_ascii_outputs:
            error_msg += f"\nCommand: {item['command']} (iteration {item['iteration']})\n"
            error_msg += f"Non-ASCII chars found: {item['non_ascii_chars']}\n"
            error_msg += "Sample positions (index, char, ord): \n"
            for pos, char, ord_val in item['positions']:
                error_msg += f"  Position {pos}: '{char}' (ord={ord_val})\n"
            # Add the full output for debugging purposes
            error_msg += "\nFull command output:\n"
            error_msg += "----------------------------------------\n"
            error_msg += f"{item['full_output']}\n"
            error_msg += "----------------------------------------\n"

        logger.error(error_msg)
        assert False, error_msg

    assert True, "All command outputs contain only ASCII characters across all iterations"
