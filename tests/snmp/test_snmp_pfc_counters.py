"""
=============================================================================
Module: snmp
File: test_snmp_pfc_counters.py
=============================================================================

Description:
    This test module validates Priority Flow Control (PFC) counter reporting
    via SNMP on SONiC switches. It verifies that all Ethernet interfaces expose
    required PFC counters through SNMP including per-priority statistics for
    PFC requests and indications.

Test Intent:
    - test_snmp_pfc_counters: Validates all Ethernet interfaces (excluding
      management ports) expose required PFC SNMP counters - cpfcIfRequests,
      cpfcIfIndications, requestsPerPriority, and indicationsPerPriority

Topology:
    - Supported: any topology, t1-multi-asic
    - Device type: vs (virtual switch)

Fixtures Used:
    - duthosts: All DUT hosts in testbed
    - enum_rand_one_per_hwsku_frontend_hostname: Randomly selected frontend DUT
    - localhost: Local connection for SNMP queries
    - creds_all_duts: SNMP credentials

Dependencies:
    - tests.common.helpers.snmp_helpers: SNMP fact collection
    - PFC SNMP MIB extension

Notes:
    - Required PFC counters per interface:
      - cpfcIfRequests: Total PFC requests sent
      - cpfcIfIndications: Total PFC frames received
      - requestsPerPriority: PFC requests per priority (0-7)
      - indicationsPerPriority: PFC indications per priority (0-7)
    - Management ports excluded (names starting with 'eth')
    - Arista 7060X6 platform: PT0 ports skipped (management interfaces)
    - Test validates Ethernet interfaces only (filters by description)
    - Failure if any Ethernet port missing required PFC counters
=============================================================================
"""

import pytest
from tests.common.helpers.snmp_helpers import get_snmp_facts

pytestmark = [
    pytest.mark.topology('any', 't1-multi-asic'),
    pytest.mark.device_type('vs')
]


def test_snmp_pfc_counters(duthosts, enum_rand_one_per_hwsku_frontend_hostname, localhost, creds_all_duts):
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]

    hostip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']

    snmp_facts = get_snmp_facts(
        duthost, localhost, host=hostip, version="v2c",
        community=creds_all_duts[duthost.hostname]["snmp_rocommunity"], wait=True)['ansible_facts']

    # Get the hardware SKU of the DUT
    hwsku = duthost.facts.get('hwsku', '')

    # Check PFC counters
    # Ignore management ports, assuming the names starting with 'eth', eg. eth0
    for _, v in list(snmp_facts['snmp_interfaces'].items()):
        desc = v.get('description', '')
        name = v.get('name', '')

        if 'Ethernet' not in desc:
            continue

        # Skip management ports for Arista 7060x6 platforms
        if 'Arista-7060X6' in hwsku and 'PT0' in desc:
            continue

        # Check for required PFC counters
        required_keys = ['cpfcIfRequests', 'cpfcIfIndications', 'requestsPerPriority', 'indicationsPerPriority']
        if not all(key in v for key in required_keys):
            pytest.fail(f"Port {name} (desc: '{desc}') missing PFC counters: {required_keys}")
