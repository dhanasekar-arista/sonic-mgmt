"""
=============================================================================
Module: cacl
File: test_ebtables_application.py
=============================================================================

Description:
    This test verifies that ebtables (Ethernet bridge tables) rules are
    correctly applied on the DUT during initialization. It validates Layer 2
    filtering rules that control bridge traffic, particularly for blocking
    specific MAC address types and protocol frames.

Test Intent:
    - test_ebtables_application: Validates that all expected ebtables rules
      are present in the FORWARD chain, including rules to drop broadcast/
      multicast traffic, ARP packets, and VLAN-encapsulated ARP frames.
      Ensures no unexpected rules exist on the device.

Topology:
    any - This test can run on any topology configuration

Fixtures Used:
    - duthosts: Multi-DUT fixture providing access to all DUT hosts
    - enum_rand_one_per_hwsku_hostname: Randomly selects one DUT per hardware SKU
    - enum_asic_index: Enumerates ASIC indices for multi-ASIC platforms

Dependencies:
    - pytest: Test framework
    - tests.common.helpers.assertions: Custom assertion helpers (pytest_assert)
    - ebtables: Ethernet bridge filtering utility on DUT

Notes:
    - Test is disabled for loganalyzer to prevent false positives
    - Expected rules include blocking BGA (Broadcast Group Address), ARP,
      VLAN-encapsulated ARP, and Multicast destinations
    - Multi-ASIC platforms are supported through enum_asic_index
    - Rules are compared as sets to detect both missing and unexpected rules
=============================================================================
"""

import pytest
from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.disable_loganalyzer,  # disable automatic loganalyzer globally
    pytest.mark.topology('any')
]


def generate_expected_rules(duthost):
    ebtables_rules = []
    # Default policies
    ebtables_rules.append("-d BGA -j DROP")
    ebtables_rules.append("-p ARP -j DROP")
    ebtables_rules.append("-p 802_1Q --vlan-encap ARP -j DROP")
    ebtables_rules.append("-d Multicast -j DROP")
    return ebtables_rules


def test_ebtables_application(duthosts, enum_rand_one_per_hwsku_hostname, enum_asic_index):
    """
    Test case to ensure ebtables rules are applied are correctly on DUT during init

    This is done by generating our own set of expected ebtables
    rules based on the DuT's configuration and comparing them against the
    actual ebtables rules on the DuT.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    expected_ebtables_rules = generate_expected_rules(duthost)

    stdout = duthost.asic_instance(enum_asic_index).command("sudo ebtables -L FORWARD")["stdout"]
    ebtables_rules = stdout.strip().split("\n")
    actual_ebtables_rules = [rule.strip().replace("0806", "ARP") for rule in ebtables_rules if rule.startswith('-')]

    # Ensure all expected ebtables rules are present on the DuT
    missing_ebtables_rules = set(expected_ebtables_rules) - set(actual_ebtables_rules)
    pytest_assert(len(missing_ebtables_rules) == 0, "Missing expected ebtables rules: {}"
                  .format(repr(missing_ebtables_rules)))

    # Ensure there are no unexpected ebtables rules present on the DuT
    unexpected_ebtables_rules = set(actual_ebtables_rules) - set(expected_ebtables_rules)
    pytest_assert(len(unexpected_ebtables_rules) == 0, "Unexpected ebtables rules: {}"
                  .format(repr(unexpected_ebtables_rules)))
