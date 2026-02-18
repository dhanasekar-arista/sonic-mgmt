"""
=============================================================================
Module: vxlan
File: test_vnet_route_leak.py
=============================================================================

Description:
    This test validates VNET route leaking functionality on Mellanox ASICs.
    It verifies that VNET routes are properly advertised to BGP neighbors,
    ensuring route redistribution between VNETs and the global routing table.

Test Intent:
    - test_vnet_route_leak: Validates that VNET routes are correctly leaked
      and advertised to BGP neighbors by:
        * Setting up VNET configuration with VxLAN tunnels
        * Verifying BGP sessions are established
        * Confirming VNET routes appear in BGP advertised routes
        * Checking route advertisement to all expected BGP neighbors

Topology:
    t0 (Mellanox ASIC only)

Fixtures Used:
    - configure_dut: Module-scoped fixture that applies VNET configuration,
      backs up config_db.json, and performs cleanup on teardown
    - minigraph_facts: Minigraph information
    - duthosts: Multi-DUT fixture
    - rand_one_dut_hostname: Random DUT selection
    - vnet_config: VNET configuration dictionary
    - vnet_test_params: VNET test parameters

Dependencies:
    - tests.common.helpers.assertions: For pytest assertions
    - tests.common.utilities: For wait_until polling
    - .vnet_utils: VNET configuration and cleanup utilities
    - .vnet_constants: VNET-related constants
    - tests.common.config_reload: For config reload operations

Notes:
    - Mellanox ASIC specific test
    - BGP wait timeout: 240 seconds
    - BGP poll rate: 10 seconds
    - Backs up and restores config_db.json during test
    - Restarts BGP service during cleanup
    - Falls back to config_reload if BGP sessions don't restore
    - Validates route leaking via "show ip bgp neighbor advertised-routes"
    - Uses regex to parse BGP neighbor IPs and advertised routes
    - Cleanup can be skipped via CLEANUP_KEY parameter
=============================================================================
"""
import logging
import pytest
import re

from collections import defaultdict
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until
from .vnet_constants import CLEANUP_KEY
from .vnet_utils import cleanup_vnet_routes, cleanup_dut_vnets, cleanup_vxlan_tunnels, \
    apply_dut_config_files, generate_dut_config_files
from tests.common.config_reload import config_reload

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology("t0"),
    pytest.mark.asic("mellanox")
]

BGP_WAIT_TIMEOUT = 240
BGP_POLL_RATE = 10

TESTING_STATUS = "Testing"
CLEANUP_STATUS = "Cleanup"

SHOW_VNET_ROUTES_CMD = "show vnet routes all"
SHOW_BGP_SUMMARY_CMD = "show ip bgp summary"
SHOW_BGP_ADV_ROUTES_CMD_TEMPLATE = "show ip bgp neighbor {} advertised-routes"
RESTART_BGP_CMD = "sudo systemctl restart bgp"
CONFIG_SAVE_CMD = "sudo config save -y"
BACKUP_CONFIG_DB_CMD = "sudo cp /etc/sonic/config_db.json /etc/sonic/config_db.json.route_leak_orig"
RESTORE_CONFIG_DB_CMD = "sudo cp /etc/sonic/config_db.json.route_leak_orig /etc/sonic/config_db.json"
DELETE_BACKUP_CONFIG_DB_CMD = "sudo rm /etc/sonic/config_db.json.route_leak_orig"

BGP_ERROR_TEMPLATE = "BGP sessions not established after {} seconds"
LEAKED_ROUTES_TEMPLATE = "Leaked routes: {}"


@pytest.fixture(scope="module")
def configure_dut(request, minigraph_facts, duthosts, rand_one_dut_hostname, vnet_config, vnet_test_params):
    """
    Setup/teardown fixture for VNET route leak test

    During the setup portion, generates VNET VxLAN configurations and applies them to the DUT
    During the teardown portion, removes all previously pushed VNET VxLAN information from the DUT

    Args:
        minigraph_facts: Minigraph information
        duthost: DUT host object
        vnet_config: Dictionary containing VNET configuration information
        vnet_test_params: Dictionary containing VNET test parameters
    """
    duthost = duthosts[rand_one_dut_hostname]

    logger.info("Backing up config_db.json")
    duthost.shell(BACKUP_CONFIG_DB_CMD)

    num_routes = request.config.option.num_routes
    duthost.shell("sonic-clear fdb all")
    generate_dut_config_files(duthost, minigraph_facts,
                              vnet_test_params, vnet_config)
    apply_dut_config_files(duthost, vnet_test_params, num_routes)

    # In this case yield is used only to separate this fixture into setup and teardown portions
    yield

    if vnet_test_params[CLEANUP_KEY]:
        logger.info("Restoring config_db.json")
        duthost.shell(RESTORE_CONFIG_DB_CMD)
        duthost.shell(DELETE_BACKUP_CONFIG_DB_CMD)

        cleanup_vnet_routes(duthost, vnet_test_params, num_routes)
        cleanup_dut_vnets(duthost, vnet_config)
        cleanup_vxlan_tunnels(duthost, vnet_test_params)

        logger.info("Restarting BGP and waiting for BGP sessions")
        duthost.shell(RESTART_BGP_CMD)

        if not wait_until(BGP_WAIT_TIMEOUT, BGP_POLL_RATE, 0, bgp_connected, duthost):
            logger.warning("BGP sessions not up {} seconds after BGP restart, restoring with `config_reload`".format(
                BGP_WAIT_TIMEOUT))
            config_reload(duthost)
    else:
        logger.info("Skipping cleanup")


def get_bgp_neighbors(duthost):
    """
    Retrieve IPs of BGP neighbors

    Args:
        duthost: DUT host object

    Returns:
        A Python list containing the IP addresses of all BGP neighbors as strings
    """

    # Match only IP addresses at the beginning of the line
    # Only IP addresses of neighbors should be matched by this
    bgp_neighbor_addr_regex = re.compile(r"^([0-9]{1,3}\.){3}[0-9]{1,3}")

    bgp_summary = duthost.shell(SHOW_BGP_SUMMARY_CMD)["stdout"].split("\n")
    logger.debug("BGP Summary: {}".format(bgp_summary))

    bgp_neighbors = []

    for line in bgp_summary:
        matched = bgp_neighbor_addr_regex.match(line)

        if matched:
            bgp_neighbors.append(str(matched.group(0)))

    return bgp_neighbors


def bgp_connected(duthost):
    """
    Checks if BGP connections are up

    BGP connections are "up" once they have received all prefixes (6400) from all neighbors

    Args:
        duthost: DUT host object

    Returns:
        True if BGP sessions are up, False otherwise
    """

    bgp_neighbors = get_bgp_neighbors(duthost)

    if not bgp_neighbors:
        return False

    return duthost.check_bgp_session_state(bgp_neighbors)


def get_leaked_routes(duthost):
    """
    Gets all VNET routes and checks that they are not advertised to any BGP neighbors

    Args:
        duthost: DUT host object

    Returns:
        A defaultdict where each key is a BGP neighbor that has had routes leaked
        (formatted as "Neighbor <IP address>") to it and each value is a Python list
        of VNET routes (as strings) that were leaked to that neighbor.
        Neighbors that did not have routes leaked to them are not included.
    """

    vnet_routes = duthost.shell(SHOW_VNET_ROUTES_CMD)["stdout"].split("\n")
    logger.debug("VNET prefixes: {}".format(vnet_routes))

    vnet_prefixes = []

    for line in vnet_routes:
        # Ignore header lines and separators
        # All other lines will contain numbers in the form of an IP address/prefix,
        # which is the information we want to extract
        if any(char.isdigit() for char in line):
            vnet_prefixes.append(line.split()[1])

    bgp_neighbors = get_bgp_neighbors(duthost)

    leaked_routes = defaultdict(list)

    for neighbor in bgp_neighbors:
        adv_routes = duthost.shell(
            SHOW_BGP_ADV_ROUTES_CMD_TEMPLATE.format(neighbor))["stdout"]

        for prefix in vnet_prefixes:
            if prefix in adv_routes:
                leaked_routes["Neighbor {}".format(
                    neighbor)].append(str(prefix))

    return leaked_routes


def test_vnet_route_leak(configure_dut, duthosts, rand_one_dut_hostname):
    """
    Test case for VNET route leak check

    Gets a list of all VNET routes programmed to the DUT, and a list of all BGP neighbors
    Verifies that no VNET routes are being advertised to BGP neighbors

    Restarts the BGP service and checks for leaked routes again

    Performs `config reload` and checks for leaked routes again

    Args:
        configure_dut: Pytest fixture to prepare DUT for testing
        duthost: DUT host object
    """
    duthost = duthosts[rand_one_dut_hostname]

    leaked_routes = get_leaked_routes(duthost)
    pytest_assert(not leaked_routes,
                  LEAKED_ROUTES_TEMPLATE.format(leaked_routes))

    logger.info("Restarting BGP")
    duthost.shell(RESTART_BGP_CMD)

    pytest_assert(wait_until(BGP_WAIT_TIMEOUT, BGP_POLL_RATE, 0,
                  bgp_connected, duthost), BGP_ERROR_TEMPLATE.format(BGP_WAIT_TIMEOUT))

    leaked_routes = get_leaked_routes(duthost)
    pytest_assert(not leaked_routes,
                  LEAKED_ROUTES_TEMPLATE.format(leaked_routes))

    logger.info("Saving and reloading CONFIG_DB")
    duthost.shell(CONFIG_SAVE_CMD)
    config_reload(duthost)

    pytest_assert(wait_until(BGP_WAIT_TIMEOUT, BGP_POLL_RATE, 0,
                  bgp_connected, duthost), BGP_ERROR_TEMPLATE.format(BGP_WAIT_TIMEOUT))

    leaked_routes = get_leaked_routes(duthost)
    pytest_assert(not leaked_routes,
                  LEAKED_ROUTES_TEMPLATE.format(leaked_routes))
