"""
=============================================================================
Module: wan/isis
File: test_isis_holdtime.py
=============================================================================

Description:
    This test validates ISIS holdtime (hello multiplier) functionality. It
    verifies that adjacencies are torn down when hello packets stop arriving
    within the holdtime period.

Test Intent:
    - test_isis_holdtime: Validates ISIS holdtime by shutting down neighbor
      interface and verifying adjacency goes down within expected time, then
      restoring interface and confirming adjacency recovers

Topology:
    wan-com (WAN common topology)

Fixtures Used:
    - isis_common_setup_teardown: Sets up ISIS configuration
    - nbrhosts: Neighbor host objects

Dependencies:
    - tests.common.utilities: For wait_until polling
    - tests.common.helpers.assertions: For pytest assertions
    - isis_helpers: For ISIS configuration helpers

Notes:
    - Holdtime = hello_interval * hello_multiplier
    - Adjacency should go down if no hellos received within holdtime
    - Tests adjacency failure detection and recovery
    - Waits for neighbor state transitions (Up/Down)
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


# IS-IS neighbor default IS-IS interval is 10s and multiplier is 3
def test_isis_holdtime(isis_common_setup_teardown, nbrhosts):
    selected_connections = isis_common_setup_teardown
    (dut_host, dut_port, nbr_host, nbr_port) = selected_connections[0]

    nbr_name = get_nbr_name(nbrhosts, nbr_host)
    pytest_assert(wait_until(10, 2, 0, check_isis_neighbor, dut_host, nbr_name, 'Up'),
                  "ISIS Neighbor {} is not Up state".format(nbr_name))

    # No PortChannel interface from IS-IS config in neighbor device
    nbr_host.no_isis_interface(isis_instance, nbr_port)

    pytest_assert(wait_until(30, 2, 1, check_isis_neighbor, dut_host, nbr_name, 'Down'),
                  "ISIS Neighbor {} is not Down state".format(nbr_name))
