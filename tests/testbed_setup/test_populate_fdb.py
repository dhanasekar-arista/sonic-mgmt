"""
=============================================================================
Module: testbed_setup
File: test_populate_fdb.py
=============================================================================

Description:
    This test file populates the FDB (Forwarding Database) table on the DUT with
    MAC address entries by sending packets from the PTF. It's primarily used as
    a testbed setup/initialization step to ensure the DUT has learned MAC addresses
    for all connected ports before running other tests that depend on proper L2
    forwarding state.

Test Intent:
    - test_populate_fdb: Populates the DUT's FDB table with MAC address entries
      for all active ports by using the populate_fdb fixture, which sends packets
      from PTF to DUT on all ports to trigger MAC address learning. This ensures
      the FDB is in a known state before subsequent tests that depend on L2
      forwarding, preventing test failures due to incomplete MAC address tables.

Topology:
    t0, m0, mx (standard topologies with VLAN configurations)

Fixtures Used:
    - populate_fdb: Module-scoped fixture that sends packets from PTF to DUT on
      all member ports to populate the FDB table with MAC addresses, ensuring
      complete MAC address learning across all active interfaces
    - copy_ptftests_directory: Copies PTF test scripts to PTF host (imported but
      likely used indirectly by populate_fdb)

Dependencies:
    - pytest: Test framework
    - tests.common.fixtures.ptfhost_utils: PTF host utilities

Notes:
    - This is primarily a setup test, not a validation test
    - The test itself has no assertions (pass statement only)
    - Actual FDB population logic is in the populate_fdb fixture
    - Commonly run before test suites that depend on L2 forwarding
    - Sends packets on all VLAN member ports
    - Ensures bidirectional MAC learning (DUT learns PTF MACs)
    - Important for tests involving: VLAN forwarding, FDB aging, L2 switching
    - Typically one of the first tests run in a test session
    - May be skipped if FDB is already populated from previous test runs
=============================================================================
"""
import pytest

from tests.common.fixtures.ptfhost_utils import copy_ptftests_directory   # noqa: F401

pytestmark = [
    pytest.mark.topology('t0', 'm0', 'mx')
]


def test_populate_fdb(populate_fdb):
    """
        Populates DUT FDB entries

        Args:
            request: pytest request object
            duthost (AnsibleHost): Device Under Test (DUT)
            ptfhost (AnsibleHost): Packet Test Framework (PTF)

        Returns:
            None
    """
    pass
