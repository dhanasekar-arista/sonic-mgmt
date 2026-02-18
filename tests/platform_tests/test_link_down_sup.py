"""
=============================================================================
Module: platform_tests
File: test_link_down_sup.py
=============================================================================

Description:
    T2 chassis supervisor reboot test validating that fanout switch links properly
    go down when supervisor reboots, then come back up when supervisor and line cards
    recover. Ensures proper link state synchronization across chassis.

Test Intent:
    - test_link_down_on_sup_reboot: Verify fanout links go down on supervisor reboot
      and come back up after supervisor and all line cards recover

Topology:
    T2 modular chassis topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - enum_supervisor_dut_hostname: Selects supervisor DUT
    - localhost: Localhost connection
    - conn_graph_facts: Connection graph for fanout mapping
    - fanouthosts: Fanout switch fixture
    - xcvr_skip_list: Transceiver skip list

Dependencies:
    - SafeThreadPoolExecutor for parallel link status checks
    - reboot and wait_for_startup for reboot operations
    - get_max_to_reboot for timeout calculation
    - check_interfaces_and_services_all_lcs for line card validation
    - fanout_hosts_and_ports for fanout mapping
    - link_status_on_host for link status validation

Notes:
    - Test skips on single-host DUT (requires multi-DUT T2 chassis)
    - Loganalyzer disabled (expected error logs during supervisor reboot)
    - Validates all fanout links down after supervisor reboot
    - Waits for supervisor recovery
    - Validates all line cards recover and services healthy
    - Confirms all fanout links back up after full recovery
    - Uses parallel execution for efficiency on multi-host validation
    - max_time_to_reboot calculated from platform reboot control
    - Verifies link status across all frontend nodes and fanouts
=============================================================================
"""
import logging
import pytest

from tests.common.helpers.multi_thread_utils import SafeThreadPoolExecutor
from tests.common.reboot import reboot, wait_for_startup
from tests.platform_tests.utils import get_max_to_reboot, check_interfaces_and_services_all_lcs, \
    fanout_hosts_and_ports, link_status_on_host

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t2'),
    pytest.mark.disable_loganalyzer,
]


def multi_duts_and_ports(duthosts):
    """
    For multi-host
    Returns:
            dict of {{duthost1, [ports]}, {duthost2, [ports]}, ...}
    """
    duts_and_ports = {}
    for duthost in duthosts.frontend_nodes:
        ports = duthost.ports_list()
        duts_and_ports[duthost] = ports
    return duts_and_ports


def link_status_on_all_fanouts(fanouts_and_ports, max_time_to_reboot, up=True):
    """
    Return:
        True: if up=True, and all links on all fanout hosts are up
              or
              if up=False, and all link on all fanout hosts are down
    """
    link_status_on_host(fanouts_and_ports, max_time_to_reboot, up=up)
    logger.info("All interfaces on all fanouts are {}!".format('up' if up else 'down'))
    return True


def test_link_down_on_sup_reboot(duthosts, localhost, enum_supervisor_dut_hostname,
                                 conn_graph_facts, fanouthosts, xcvr_skip_list):
    if len(duthosts.nodes) == 1:
        pytest.skip("Skip single-host dut for this test")

    duthost = duthosts[enum_supervisor_dut_hostname]
    max_time_to_reboot = get_max_to_reboot(duthost, 'test_link_down_sup.py')

    # There are some errors due to reboot happened before this test file for some reason,
    # and SUP may not have enough time to recover all dockers and the wait for process wait for 300 secs in
    # pytest_assert(wait_until(300, 20, 0, _all_critical_processes_healthy, dut),
    # would not be enough. _all_critical_processes_healthy only validates processes are started
    # Wait for ssh port to open up on the DUT
    wait_for_startup(duthost, localhost, 0, max_time_to_reboot)

    hostname = duthost.hostname
    # Before test, check all interfaces and services are up on all linecards
    check_interfaces_and_services_all_lcs(duthosts, conn_graph_facts, xcvr_skip_list)

    duts_and_ports = multi_duts_and_ports(duthosts)
    fanouts_and_ports = fanout_hosts_and_ports(fanouthosts, duts_and_ports)

    # Also make sure fanout hosts' links are up
    link_status_on_all_fanouts(fanouts_and_ports, max_time_to_reboot)

    # Get a dut uptime before reboot
    dut_uptime_before = duthost.get_up_time()

    # Reboot RP should reboot both RP&LC, should detect all links on all linecards go down
    reboot(duthost, localhost, wait_for_ssh=False)

    # Also make sure fanout hosts' links are down
    link_status_on_all_fanouts(fanouts_and_ports, max_time_to_reboot, up=False)

    # Wait for ssh port to open up on the SUP
    wait_for_startup(duthost, localhost, 0, max_time_to_reboot)
    # Wait for ssh port to open up on the linecards
    with SafeThreadPoolExecutor(max_workers=8) as executor:
        for linecard in duthosts.frontend_nodes:
            executor.submit(wait_for_startup, linecard, localhost, 0, max_time_to_reboot)

    dut_uptime = duthost.get_up_time()
    logger.info('DUT {} up since {}'.format(hostname, dut_uptime))
    rebooted = float(dut_uptime_before.strftime("%s")) != float(dut_uptime.strftime("%s"))
    assert rebooted, "Device {} did not reboot".format(hostname)

    # Verify that the links are all LCs are up
    check_interfaces_and_services_all_lcs(duthosts, conn_graph_facts, xcvr_skip_list)

    # Also make sure fanout hosts' links are up
    link_status_on_all_fanouts(fanouts_and_ports, max_time_to_reboot)
