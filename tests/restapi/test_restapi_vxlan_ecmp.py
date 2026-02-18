"""
=============================================================================
Module: restapi
File: test_restapi_vxlan_ecmp.py
=============================================================================

Description:
    Tests REST API operations for VxLAN ECMP (Equal-Cost Multi-Path) route
    management in SONiC VNET. Validates adding, retrieving, and deleting
    VxLAN tunnel routes with multiple next-hops through REST API.

Test Intent:
    - test_vxlan_ecmp_multirequest: Stress tests REST API by repeatedly adding
      and deleting VxLAN routes with ECMP next-hops. Test sequence:
      1. Add 2 initial routes (A, B)
      2. Loop 10 times:
         - Verify routes A, B exist
         - Add 3 more routes (C, D, E) with ECMP next-hops
         - Verify all 5 routes (A, B, C, D, E) exist
         - Delete routes C, D, E
      3. Delete initial routes A, B
      4. Verify all routes deleted
      This emulates common production scenarios with frequent route updates.

Topology:
    t0, t1 topologies

Fixtures Used:
    - construct_url: REST API base URL fixture
    - vlan_members: VLAN member configuration fixture
    - duthost: DUT host instance for CLI verification

Dependencies:
    - restapi_operations.Restapi: REST API operation wrapper class
    - tests.common.utilities.wait_until: Polling utility for route verification

Notes:
    - Disables loganalyzer for these tests
    - Uses client certificate: restapiclient.crt with key restapiclient.key
    - ROUTES_DATA contains 5 test routes with ECMP next-hops
    - Each route has comma-separated next-hops (e.g., "100.78.60.37,100.78.61.37")
    - IP prefixes: 10.1.0.1/32 through 10.1.0.5/32
    - Initial routes: routes 0 and 4 (10.1.0.1/32 and 10.1.0.5/32)
    - Additional routes: routes 1, 2, 3 (10.1.0.2/32, 10.1.0.3/32, 10.1.0.4/32)
    - Uses "show vnet routes tunnel" to verify route installation
    - Uses "show vnet alias" to map VNET alias to VNET name
    - get_vnet_name() retrieves VNET name from alias
    - get_vnet_routes() parses CLI output to list format for comparison
    - Tests both single route operations and batch operations
=============================================================================
"""
import pytest
import logging
import json

from tests.common.helpers.assertions import pytest_assert
from restapi_operations import Restapi
from tests.common.utilities import wait_until


logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t0', 't1'),
    pytest.mark.disable_loganalyzer
]

CLIENT_CERT = 'restapiclient.crt'
CLIENT_KEY = 'restapiclient.key'

SHOW_VNET_ROUTES_CMD = "show vnet routes tunnel"
SHOW_VNET_ALIAS_CMD = "show vnet alias"

ROUTES_DATA = [
    {"nexthop": "100.78.60.37,100.78.61.37", "ip_prefix": "10.1.0.1/32"},
    {"nexthop": "100.78.60.38,100.78.61.38", "ip_prefix": "10.1.0.2/32"},
    {"nexthop": "100.78.60.39,100.78.61.39", "ip_prefix": "10.1.0.3/32"},
    {"nexthop": "100.78.60.40,100.78.61.40", "ip_prefix": "10.1.0.4/32"},
    {"nexthop": "100.78.60.41,100.78.61.41", "ip_prefix": "10.1.0.5/32"}
]

INITIAL_ROUTES = [ROUTES_DATA[0], ROUTES_DATA[4]]

restapi = Restapi(CLIENT_CERT, CLIENT_KEY)


def get_vnet_name(duthost, vnet_alias):
    """
    Gets the alias of a VNET
    """
    vnet_alias_output = duthost.shell(SHOW_VNET_ALIAS_CMD)["stdout"].split("\n")
    for line in vnet_alias_output[2:]:
        alias, vnet_name, *_ = line.split()
        if alias == vnet_alias:
            return vnet_name
    return None


def get_vnet_routes(duthost, vnet_alias):
    """
    Gets all VNET routes and returns them as a list in API format (nexthop first, then ip_prefix)
    """
    vnet_routes_output = duthost.shell(SHOW_VNET_ROUTES_CMD)["stdout"].split("\n")
    vnet_routes = []
    expected_vnet_name = get_vnet_name(duthost, vnet_alias)

    for line in vnet_routes_output[2:]:
        if not any(char.isdigit() for char in line):
            continue
        vnet_name, ip_prefix, nexthop, *_ = line.split()
        if vnet_name == expected_vnet_name:
            vnet_routes.append({"nexthop": nexthop, "ip_prefix": ip_prefix})

    return vnet_routes


'''
This test runs the following sequence to stress the restapi behaviour.
add 2 routes A,B
loop 10 times
    verify A,B by reading routes.
    add 3 more routes C,D,E
    verify 5 routes by reading routes A, B, C, D, E 10 times.
    delete the 3 added routes. C, D, E
delete the last 2 routes A, B
verify all routes deleted.
'''


def test_vxlan_ecmp_multirequest(construct_url, vlan_members, duthost):
    # test to emulate common scenario in pilot.

    # Create Generic tunnel
    params = '{"ip_addr": "100.78.1.1"}'
    logger.info("Creating default vxlan tunnel")
    r = restapi.post_config_tunnel_decap(construct_url, params)
    pytest_assert(r.status_code == 204)

    # Create VNET
    params = '{"vnid": 703}'
    logger.info("Creating VNET vnet-guid-3 with vnid: 703")
    r = restapi.post_config_vrouter_vrf_id(construct_url, 'vnet-default', params)
    pytest_assert(r.status_code == 204)

    # Verify VNET has been created
    r = restapi.get_config_vrouter_vrf_id(construct_url, 'vnet-default')
    pytest_assert(r.status_code == 200)
    logger.info(r.json())
    expected = '{"attr": {"vnid": 703}, "vnet_id": "vnet-default"}'
    pytest_assert(r.json() == json.loads(expected))
    logger.info("VNET with vnet_id: vnet-guid-4 has been successfully created with vnid: 7039115")

    # Add first 2 routes
    params = '[{"cmd": "add", "ip_prefix": "10.1.0.1/32", "nexthop": "100.78.60.37,100.78.61.37"}, \
                {"cmd": "add", "ip_prefix": "10.1.0.5/32", "nexthop": "100.78.60.41,100.78.61.41"}]'
    logger.info("Adding routes with vnid: 703 to VNET vnet-default")
    r = restapi.patch_config_vrouter_vrf_id_routes(construct_url, 'vnet-default', params)
    pytest_assert(r.status_code == 204)
    # Wait to apply the patch
    pytest_assert(wait_until(10, 2, 0, lambda: get_vnet_routes(duthost, 'vnet-default') == INITIAL_ROUTES))

    for i in range(1, 10):
        # Read the 2 routes
        params = '{}'
        r = restapi.get_config_vrouter_vrf_id_routes(construct_url, 'vnet-default', params)
        pytest_assert(r.status_code == 200)
        logger.info(r.json())
        for route in INITIAL_ROUTES:
            pytest_assert(route in r.json(), "i={}, {} not in r.json".format(i, route))
        logger.info("Routes with vnid: 703 to VNET vnet-default have been added successfully")

        # Add 3 more routes
        params = '[{"cmd": "add", "ip_prefix": "10.1.0.2/32", "nexthop": "100.78.60.38,100.78.61.38"}, \
                    {"cmd": "add", "ip_prefix": "10.1.0.3/32", "nexthop": "100.78.60.39,100.78.61.39"}, \
                    {"cmd": "add", "ip_prefix": "10.1.0.4/32", "nexthop": "100.78.60.40,100.78.61.40"}]'
        logger.info("Adding routes with vnid: 703 to VNET vnet-default")
        r = restapi.patch_config_vrouter_vrf_id_routes(construct_url, 'vnet-default', params)
        pytest_assert(r.status_code == 204)
        # Wait to apply the patch
        pytest_assert(wait_until(10, 2, 0, lambda: get_vnet_routes(duthost, 'vnet-default') == ROUTES_DATA))

        # Read all the routes 10 times.
        params = '{}'
        for j in range(1, 10):
            r = restapi.get_config_vrouter_vrf_id_routes(construct_url, 'vnet-default', params)
            pytest_assert(r.status_code == 200)
            logger.info(r.json())
            for route in ROUTES_DATA:
                pytest_assert(route in r.json(), "j={}, {} not in r.json".format(j, route))
        logger.info("Routes with vnid: 703 to VNET vnet-default have been added successfully")

        # Delete  the 3 added routes
        params = '[{"cmd": "delete", "ip_prefix": "10.1.0.2/32", "nexthop": "100.78.60.38,100.78.61.38"}, \
                    {"cmd": "delete", "ip_prefix": "10.1.0.3/32", "nexthop": "100.78.60.39,100.78.61.39"}, \
                    {"cmd": "delete", "ip_prefix": "10.1.0.4/32", "nexthop": "100.78.60.40,100.78.61.40"}]'
        logger.info("Deleting routes with vnid: 703 from VNET vnet-default")
        r = restapi.patch_config_vrouter_vrf_id_routes(construct_url, 'vnet-default', params)
        pytest_assert(r.status_code == 204)
        # Wait to apply the patch
        pytest_assert(wait_until(10, 2, 0, lambda: get_vnet_routes(duthost, 'vnet-default') == INITIAL_ROUTES))

    # Verify first 2 routes
    params = '{}'
    r = restapi.get_config_vrouter_vrf_id_routes(construct_url, 'vnet-default', params)
    pytest_assert(r.status_code == 200)
    logger.info(r.json())

    for route in INITIAL_ROUTES:
        pytest_assert(route in r.json(), "{} not in r.json".format(route))
    logger.info("Routes with vnid: 703 to VNET vnet-default have been added successfully")

    # Delete routes
    params = '[{"cmd": "delete", "ip_prefix": "10.1.0.1/32", "nexthop": "100.78.60.37,100.78.61.37"}, \
                {"cmd": "delete", "ip_prefix": "10.1.0.5/32", "nexthop": "100.78.60.41,100.78.61.41"}]'
    logger.info("Deleting routes with vnid: 703 from VNET vnet-default")
    r = restapi.patch_config_vrouter_vrf_id_routes(construct_url, 'vnet-default', params)
    pytest_assert(r.status_code == 204)
    # Wait to apply the patch
    pytest_assert(wait_until(10, 2, 0, lambda: get_vnet_routes(duthost, 'vnet-default') == []))

    # Verify route absence.
    params = '{}'
    r = restapi.get_config_vrouter_vrf_id_routes(construct_url, 'vnet-default', params)
    pytest_assert(r.status_code == 200)
    logger.info(r.json())
    pytest_assert(len(r.json()) == 0)
    logger.info("Routes with vnid: 703 from VNET vnet-default have been deleted successfully")
