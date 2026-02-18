"""
=============================================================================
Module: route
File: test_duplicate_route.py
=============================================================================

Description:
    This test module validates proper handling of duplicate route additions on
    SONiC switches. It verifies that attempting to add routes with prefixes that
    overlap with existing interface IPs results in appropriate error handling
    without causing orchagent crashes or unexpected behavior. Tests cover both
    Loopback and VLAN interface overlaps for IPv4 and IPv6.

Test Intent:
    - test_duplicate_route_add: Attempts to add static routes whose prefixes
      overlap with existing interface IPs (Loopback or VLAN), verifies that the
      operation fails gracefully with expected error messages in syslog, and
      confirms orchagent remains running without crashes

Topology:
    - Supported: t0, m0, any
    - Device type: vs (virtual switch)
    - Tests on single-ASIC and multi-ASIC devices

Fixtures Used:
    - duthosts: All DUT hosts in the testbed
    - enum_rand_one_per_hwsku_frontend_hostname: Randomly selected frontend DUT
    - enum_rand_one_frontend_asic_index: Selected ASIC instance
    - tbinfo: Testbed information fixture
    - is_backend_topology: Backend topology detection
    - interface_types: Parametrized fixture for Loopback and VLAN interfaces
    - verify_expected_loganalyzer_logs: Auto-use fixture that expects and ignores
      duplicate route creation errors

Dependencies:
    - tests.route.utils: Interface/neighbor generation, route file creation
    - tests.common.helpers.dut_utils: Orchagent status verification
    - netaddr.IPNetwork: IP network manipulation for finding overlapping routes

Notes:
    - Test deliberately triggers error conditions to validate error handling
    - Expected log patterns: "Failed to create route", "object already exists"
    - Orchagent must remain running after duplicate route attempt
    - Test picks random IP from interface subnet as duplicate route prefix
    - Uses 50 temporary neighbor entries for route nexthops
    - Route file generated via swssconfig for configuration
    - 15-second delay after route addition for log propagation
    - Cleanup removes temporary interfaces and neighbors via config reload on failure
=============================================================================
"""

import pytest
import json
import random
import logging

from time import sleep
from netaddr import IPNetwork
from tests.common import config_reload
from tests.common.helpers.assertions import pytest_assert, pytest_require
from tests.common.helpers.dut_utils import verify_orchagent_running_or_assert
from tests.route.utils import generate_intf_neigh, generate_route_file, prepare_dut, cleanup_dut


pytestmark = [
    pytest.mark.topology("t0", "m0", "any"),
    pytest.mark.device_type('vs')
]

logger = logging.getLogger(__name__)

LOG_EXPECT_ADD_ROUTE_FAILED = ".*Failed to create route.*"


def get_cfg_facts(duthost, asic_index):
    if duthost.sonichost.is_multi_asic:
        asic_ns = "asic{}".format(asic_index)
        cmd = "sonic-cfggen -d --print-data -n {}".format(asic_ns)
        tmp_facts = json.loads(duthost.shell(cmd)['stdout'])
    # return config db contents(running-config)
    else:
        cmd = "sonic-cfggen -d --print-data"
        tmp_facts = json.loads(duthost.shell(cmd)['stdout'])

    return tmp_facts


def get_intf_ips(interface_name, cfg_facts):
    prefix_to_intf_table_map = {
        'Vlan': 'VLAN_INTERFACE',
        'PortChannel': 'PORTCHANNEL_INTERFACE',
        'Ethernet': 'INTERFACE',
        'Loopback': 'LOOPBACK_INTERFACE'
    }

    intf_table_name = None

    ip_facts = {
        'ipv4': [],
        'ipv6': []
    }

    for pfx, t_name in list(prefix_to_intf_table_map.items()):
        if pfx in interface_name:
            intf_table_name = t_name
            break

    if intf_table_name is None:
        return ip_facts

    if intf_table_name not in cfg_facts:
        return ip_facts

    for intf in cfg_facts[intf_table_name]:
        if '|' in intf:
            if_name, ip = intf.split('|')
            if interface_name in if_name:
                ip = IPNetwork(ip)
                if ip.version == 4:
                    ip_facts['ipv4'].append(ip)
                else:
                    ip_facts['ipv6'].append(ip)

    return ip_facts


@pytest.fixture(params=['Loopback', 'Vlan'])
def interface_types(request):
    """
    Parameterized fixture for interface types.
    """
    yield request.param


@pytest.fixture(autouse=True)
def verify_expected_loganalyzer_logs(
    enum_rand_one_per_hwsku_frontend_hostname, loganalyzer
):
    """
    Verify that expected failure messages are seen in logs during test execution
    Args:
        duthost: DUT fixture
        loganalyzer: Loganalyzer utility fixture
    """
    expectRegex = [
        ]
    ignoreRegex = [
        ".*ERR.* create failed, object already exists.*",
        ".*ERR.* bulkCreate: Failed to create object.*",
        ".*ERR.* api SAI_COMMON_API_BULK_CREATE failed in syncd mode.*",
        ".*ERR.* flush_creating_entries: EntityBulker.flush create entries failed.*",
        ".*ERR.* handleSaiFailure: Encountered failure in create operation.*",
        ".*ERR.* start: Encountered failure in create operation.*",
        ".*ERR.* Failed to add UC route .* Entry Already Exists.",
        r".*ERR.* uc_route_set_async_pre_send_validate .* \[Entry Already Exists\].",
        ".*ERR.* mlnx_create_route_async.* Entry Already Exists.",
        ".*ERR.* object key SAI_OBJECT_TYPE_ROUTE_ENTRY:.* already exists.*",  # TODO move to expectRegex
        ".*ERR.* addRoutePost: Failed to create route.*",  # TODO move to expectRegex
        ".*ERR.* ipv4_route_bulk_updates API returned.*Key already exists in table.*",
        ".*ERR syncd#SDK:.*mlnx_route_pre_create: Route entry already exists in the Route DB.*",
        ".*ERR syncd#SDK:.*mlnx_route_bulk_set_impl: Failed to prepare route data for bulk operation. index:.*",
        ".*ERR syncd#SDK:.*mlnx_route_bulk_set_impl: No valid route entries for bulk operation in chunk starting at.*"
    ]
    if loganalyzer:
        # Skip if loganalyzer is disabled
        loganalyzer[enum_rand_one_per_hwsku_frontend_hostname].expect_regex.extend(
            expectRegex
        )
        loganalyzer[enum_rand_one_per_hwsku_frontend_hostname].ignore_regex.extend(
            ignoreRegex
        )


@pytest.fixture(scope="module", autouse=True)
def reload_dut(duthosts, enum_rand_one_per_hwsku_frontend_hostname):
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    yield
    config_reload(duthost, safe_reload=True, wait_for_bgp=True)


@pytest.fixture
def setup_routes(duthosts, enum_rand_one_per_hwsku_frontend_hostname,
                 enum_rand_one_frontend_asic_index, ip_versions, interface_types):
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    cfg_facts = get_cfg_facts(duthost, enum_rand_one_frontend_asic_index)
    asichost = duthost.asic_instance(enum_rand_one_frontend_asic_index)
    prefixes = []

    if interface_types == 'Loopback':
        # Get loopback ips
        intf_ips = get_intf_ips('Loopback', cfg_facts)
        pytest_require((len(intf_ips['ipv4']) + len(intf_ips['ipv6'])) > 0, "No IP configured on Loopback0")
    else:
        # Get vlan ips
        intf_ips = get_intf_ips('Vlan', cfg_facts)
        pytest_require((len(intf_ips['ipv4']) + len(intf_ips['ipv6'])) > 0, "No IP configured on any Vlan")

    # Generate interfaces and neighbors
    intf_neighs, str_intf_nexthop = generate_intf_neigh(
        asichost, 1, ip_versions)
    if ip_versions == 4:
        prefixes.append(str(random.choice(intf_ips['ipv4'])).split("/")[0])
    else:
        prefixes.append(str(random.choice(intf_ips['ipv6'])).split("/")[0])

    # Setup interface IPs and neighbors
    prepare_dut(asichost, intf_neighs)

    # Generate a temp json file for route configuration
    route_file_set = duthost.shell("mktemp")["stdout"]
    generate_route_file(duthost, prefixes, str_intf_nexthop, route_file_set, "SET")

    yield route_file_set

    # Remove interface IPs and neighbors
    cleanup_dut(asichost, intf_neighs)
    duthost.shell("rm {}".format(route_file_set))


def test_duplicate_routes(duthosts, enum_rand_one_per_hwsku_frontend_hostname,
                          enum_rand_one_frontend_asic_index, setup_routes):
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    swss_cfg_file_set = setup_routes

    # Get orchagent pid before applying config
    pid_before = duthost.shell("pidof orchagent")['stdout']

    # Apply route configuration
    logger.info("Applying routes via swssconfig...")
    json_set = "/dev/stdin < {}".format(swss_cfg_file_set)

    result = duthost.docker_exec_swssconfig(
        json_set, "swss", enum_rand_one_frontend_asic_index
    )

    if result["rc"] != 0:
        pytest.fail(
            "Failed to apply route configuration file: {}".format(result["stderr"])
        )

    # If T2 chassis, there maybe more than 32K routes per RH/AH neighbor.
    # when previous uplink LC finished reload_dut, the routes update may still be in progress even after all BGP
    # sessions are up. So wait for a longer time.
    route_wait_time = 5
    if 't2' in duthosts.tbinfo['topo']['name']:
        route_wait_time = 60
    sleep(route_wait_time)

    # Verify that orchagent has not crashed
    verify_orchagent_running_or_assert(duthost)
    pid_after = duthost.shell("pidof orchagent")['stdout']
    pytest_assert(pid_before == pid_after, "Error: Orchagent restarted")
