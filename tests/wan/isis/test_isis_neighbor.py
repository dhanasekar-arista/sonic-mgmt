"""
=============================================================================
Module: wan/isis
File: test_isis_neighbor.py
=============================================================================

Description:
    This test validates ISIS (Intermediate System to Intermediate System)
    neighbor adjacency formation and state transitions in WAN topologies.
    It tests that ISIS neighbors properly transition between Up and Down
    states when interfaces are administratively shut down and brought back up.

Test Intent:
    - test_isis_neighbor: Validates ISIS neighbor state management by:
        * Verifying initial neighbor is in Up state
        * Shutting down neighbor's PortChannel and confirming Down state
        * Re-enabling neighbor's PortChannel and confirming Up state recovery
        * Shutting down DUT's PortChannel and confirming Down state
        * Re-enabling DUT's PortChannel and confirming Up state recovery

Topology:
    wan-com (WAN common topology)

Fixtures Used:
    - isis_common_setup_teardown: Sets up ISIS configuration and provides
      selected connections between DUT and neighbors
    - nbrhosts: Neighbor host objects for interaction

Dependencies:
    - tests.common.utilities: For wait_until polling
    - tests.common.helpers.assertions: For pytest assertions
    - isis_helpers: For ISIS-specific helper functions and constants

Notes:
    - Uses DEFAULT_ISIS_INSTANCE from isis_helpers
    - Polls for up to 10 seconds with 2-second intervals for state changes
    - Tests both DUT-initiated and neighbor-initiated link down scenarios
    - Verifies bidirectional ISIS adjacency formation
    - Ensures ISIS neighbor recovery after interface restoration
    - PortChannel interfaces used for ISIS neighbor connections
=============================================================================
"""
import pytest
import logging

from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from isis_helpers import DEFAULT_ISIS_INSTANCE as isis_instance
from isis_helpers import get_nbr_name


logger = logging.getLogger(__name__)


pytestmark = [
    pytest.mark.topology('wan-com'),
]


def check_isis_neighbor(duthost, nbr_name, state):
    isis_facts = duthost.isis_facts()["ansible_facts"]['isis_facts']
    if isis_instance not in isis_facts['neighbors']:
        logger.info("Failed to isis instance {} in dut {}.".format(isis_instance, duthost.hostname))
        return False

    if state == 'Up' and nbr_name not in isis_facts['neighbors'][isis_instance]:
        return False

    if state == 'Up' and isis_facts['neighbors'][isis_instance][nbr_name]['state'] == 'Up':
        return True

    if state == 'Down' and nbr_name not in isis_facts['neighbors'][isis_instance]:
        return True

    logger.info("Failed to nbr {} in dut {}.".format(nbr_name, duthost.hostname))
    return False


def test_isis_neighbor(isis_common_setup_teardown, nbrhosts):
    selected_connections = isis_common_setup_teardown
    (dut_host, dut_port, nbr_host, nbr_port) = selected_connections[0]

    nbr_name = get_nbr_name(nbrhosts, nbr_host)
    pytest_assert(wait_until(10, 2, 0, check_isis_neighbor, dut_host, nbr_name, 'Up'),
                  "ISIS Neighbor {} is not Up state".format(nbr_name))

    # Shutdown PortChannel in neighbor device
    nbr_host.shutdown(nbr_port)
    pytest_assert(wait_until(10, 2, 1, check_isis_neighbor, dut_host, nbr_name, 'Down'),
                  "ISIS Neighbor {} is not Down state".format(nbr_name))

    # No Shutdown PortChannel in neighbor device
    nbr_host.no_shutdown(nbr_port)
    pytest_assert(wait_until(10, 2, 1, check_isis_neighbor, dut_host, nbr_name, 'Up'),
                  "ISIS Neighbor {} is not Up state".format(nbr_name))

    # Shutdown PortChannel in dut device
    dut_host.shutdown(dut_port)
    pytest_assert(wait_until(10, 2, 1, check_isis_neighbor, dut_host, nbr_name, 'Down'),
                  "ISIS Neighbor {} is not Down state".format(nbr_name))

    # No Shutdown PortChannel in dut device
    dut_host.no_shutdown(dut_port)
    pytest_assert(wait_until(10, 2, 1, check_isis_neighbor, dut_host, nbr_name, 'Up'),
                  "ISIS Neighbor {} is not Up state".format(nbr_name))
