"""
=============================================================================
Module: bgp
File: test_bgp_allow_list.py
=============================================================================

Description:
    Tests BGP Allow List (prefix-list based route filtering) feature in SONiC.
    Validates route filtering with community-based and prefix-based allow lists
    with both permit and deny default actions.

Test Intent:
    - test_default_allow_list_preconfig: Verifies default BGP policy behavior
      before applying allow list configuration
    - test_allow_list: Tests allow list with permit/deny default actions, validates
      route filtering and community handling
    - test_default_allow_list_postconfig: Ensures BGP policy returns to default
      after removing allow list configuration

Topology:
    t1, m1

Fixtures Used:
    - bgp_allow_list_setup: Sets up test environment with downstream neighbors
    - load_remove_allow_list: Applies and removes allow list configuration
    - nbrhosts: Neighbor hosts fixture
    - ptfhost: PTF host for BGP monitor validation
    - bgpmon_setup_teardown: Sets up BGP monitor session

Dependencies:
    - bgp_helpers: Allow list configuration and validation functions
    - tests.common.helpers.assertions.pytest_assert

Notes:
    - Only runs on virtual switch (vs) device types
    - Tests both IPv4 and IPv6 prefix filtering
    - Validates route propagation to upstream and downstream neighbors
    - Checks community attribute handling (drop_community)
    - Uses deployment ID for allow list configuration
=============================================================================
"""

import logging
import pytest

from tests.common.helpers.assertions import pytest_assert
# Constants
from bgp_helpers import ALLOW_LIST_PREFIX_JSON_FILE, PREFIX_LISTS, TEST_COMMUNITY
# Functions
from bgp_helpers import apply_allow_list, remove_allow_list, check_routes_on_from_neighbor, get_default_action
from bgp_helpers import check_routes_on_neighbors_empty_allow_list, checkout_bgp_mon_routes, check_routes_on_neighbors
# Fixtures
from bgp_helpers import bgp_allow_list_setup, prepare_eos_routes    # noqa:F401

pytestmark = [
    pytest.mark.topology('t1', 'm1', 'c0'),
    pytest.mark.device_type('vs')
]

logger = logging.getLogger(__name__)

DEPLOYMENT_ID = '0'
ALLOW_LIST = {
    'BGP_ALLOWED_PREFIXES': {
        'DEPLOYMENT_ID|{}|{}'.format(DEPLOYMENT_ID, TEST_COMMUNITY): {
            'prefixes_v4': PREFIX_LISTS['ALLOWED_WITH_COMMUNITY'],
            'prefixes_v6': PREFIX_LISTS['ALLOWED_WITH_COMMUNITY_V6'],
            'default_action': ''
        },
        'DEPLOYMENT_ID|{}'.format(DEPLOYMENT_ID): {
            'prefixes_v4': PREFIX_LISTS['ALLOWED'],
            'prefixes_v6': PREFIX_LISTS['ALLOWED_V6'],
            'default_action': ''
        }
    }
}


@pytest.fixture
def load_remove_allow_list(duthosts, bgp_allow_list_setup, rand_one_dut_hostname, request):     # noqa:F811
    allowed_list_prefixes = ALLOW_LIST['BGP_ALLOWED_PREFIXES']
    for _, value in list(allowed_list_prefixes.items()):
        value['default_action'] = request.param

    duthost = duthosts[rand_one_dut_hostname]
    namespace = bgp_allow_list_setup['downstream_namespace']
    apply_allow_list(duthost, namespace, ALLOW_LIST, ALLOW_LIST_PREFIX_JSON_FILE)

    yield request.param

    remove_allow_list(duthost, namespace, ALLOW_LIST_PREFIX_JSON_FILE)


def check_routes_on_dut(duthost, setup_info):
    """
    Verify routes on dut
    """
    for list_name, prefixes in list(PREFIX_LISTS.items()):
        if setup_info['is_v6_topo'] and "v6" not in list_name.lower():
            continue
        for prefix in prefixes:
            dut_route = duthost.get_route(prefix, setup_info['downstream_namespace'])
            pytest_assert(dut_route, 'Route {} is not found on DUT'.format(prefix))


def test_default_allow_list_preconfig(duthosts, rand_one_dut_hostname, bgp_allow_list_setup, nbrhosts,  # noqa:F811
                                      ptfhost, bgpmon_setup_teardown):
    """
    Before applying allow list, verify bgp policy by default config
    """
    permit = True if get_default_action() == "permit" else False
    duthost = duthosts[rand_one_dut_hostname]
    # All routes should be found on from neighbor.
    check_routes_on_from_neighbor(bgp_allow_list_setup, nbrhosts)
    # All routes should be found in dut.
    check_routes_on_dut(duthost, bgp_allow_list_setup)
    # If permit is True, all routes should be forwarded and added drop_community and keep ori community.
    # If permit if False, all routes should not be forwarded.
    check_routes_on_neighbors_empty_allow_list(nbrhosts, bgp_allow_list_setup, permit)
    checkout_bgp_mon_routes(duthost, ptfhost)


@pytest.mark.parametrize('load_remove_allow_list', ["permit", "deny"], indirect=['load_remove_allow_list'])
def test_allow_list(duthosts, rand_one_dut_hostname, bgp_allow_list_setup, nbrhosts,    # noqa:F811
                    load_remove_allow_list, ptfhost, bgpmon_setup_teardown):
    permit = True if load_remove_allow_list == "permit" else False
    duthost = duthosts[rand_one_dut_hostname]
    # All routes should be found on from neighbor.
    check_routes_on_from_neighbor(bgp_allow_list_setup, nbrhosts)
    # All routes should be found in dut.
    check_routes_on_dut(duthost, bgp_allow_list_setup)
    # If permit is True, all routes should be forwarded. Routs that in allow list should not be add drop_community
    # and keep ori community.
    # If permit is False, Routes in allow_list should be forwarded and keep ori community, routes not in allow_list
    # should not be forwarded.
    check_routes_on_neighbors(nbrhosts, bgp_allow_list_setup, permit)
    checkout_bgp_mon_routes(duthost, ptfhost)


def test_default_allow_list_postconfig(duthosts, rand_one_dut_hostname, bgp_allow_list_setup,   # noqa:F811
                                       nbrhosts, ptfhost, bgpmon_setup_teardown):
    """
    After removing allow list, verify bgp policy
    """
    test_default_allow_list_preconfig(duthosts, rand_one_dut_hostname, bgp_allow_list_setup,    # noqa:F811
                                      nbrhosts, ptfhost, bgpmon_setup_teardown)
