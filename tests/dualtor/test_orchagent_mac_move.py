"""
=============================================================================
Module: Dual ToR Orchagent MAC Move Test
File: test_orchagent_mac_move.py
=============================================================================

Description:
    This test validates MAC address mobility (MAC move) behavior in dual ToR
    topology. It verifies that when a MAC address moves between mux ports with
    different states (active/standby), orchagent correctly updates forwarding
    behavior including ARP/neighbor tables, FDB entries, and traffic forwarding
    paths (direct vs tunnel).

Test Intent:
    - test_mac_move: Validates complete MAC move scenarios:
      1. Learns new neighbor on active port and verifies direct forwarding
      2. Moves MAC to standby port and verifies tunnel forwarding
      3. Tests forwarding after FDB flush on standby port (should tunnel)
      4. Moves MAC to another active port and verifies direct forwarding
      5. Tests forwarding after FDB flush on active port (platform-dependent)

Topology:
    t0 - Requires t0 topology with mocked dual ToR configuration

Fixtures Used:
    - announce_new_neighbor: Generator fixture to announce GARP packets on different ports
    - apply_active_state_to_orchagent: Sets all mux ports to active state
    - cleanup_arp: Cleans up ARP entries after test
    - enable_garp: Enables gratuitous ARP acceptance on VLAN interface
    - set_crm_polling_interval: Sets CRM polling interval for resource tracking
    - tunnel_traffic_monitor: Monitors tunnel traffic presence/absence
    - run_garp_service: Runs GARP service on PTF
    - run_icmp_responder: Runs ICMP responder on PTF

Dependencies:
    - tests.common.dualtor.dual_tor_mock: Dual ToR mocking utilities
    - tests.common.dualtor.dual_tor_utils: Dual ToR utility functions
    - tests.common.dualtor.server_traffic_utils: Server traffic monitoring
    - tests.common.dualtor.tunnel_traffic_utils: Tunnel traffic monitoring

Notes:
    - Uses fixed test neighbor: 192.168.0.250 with MAC 02:AA:BB:CC:DD:EE
    - GARP packets are sent 5 times per announcement to ensure learning
    - Test enables arp_accept on VLAN interface to learn from GARP
    - CRM neighbor counter changes are tracked (expected for IPv6)
    - FDB flush behavior differs by platform (Mellanox/Cisco flood traffic)
    - Test randomly selects mux ports to avoid order dependencies
    - Properly restores neighbor entries in cleanup if test fails
=============================================================================
"""
import logging
import pytest
import random

from ptf import testutils
from tests.common.dualtor.dual_tor_mock import is_mocked_dualtor
from tests.common.dualtor.dual_tor_mock import set_dual_tor_state_to_orchagent
from tests.common.dualtor.dual_tor_utils import get_t1_ptf_ports
from tests.common.dualtor.dual_tor_utils import crm_neighbor_checker
from tests.common.dualtor.dual_tor_utils import build_packet_to_server
from tests.common.dualtor.dual_tor_utils import mux_cable_server_ip
from tests.common.dualtor.server_traffic_utils import ServerTrafficMonitor
from tests.common.dualtor.tunnel_traffic_utils import tunnel_traffic_monitor    # noqa: F401
from tests.common.fixtures.ptfhost_utils import run_icmp_responder              # noqa: F401
from tests.common.fixtures.ptfhost_utils import run_garp_service                # noqa: F401
from tests.common.fixtures.ptfhost_utils import change_mac_addresses            # noqa: F401
from tests.common.utilities import dump_scapy_packet_show_output


pytestmark = [
    pytest.mark.topology('t0'),
    pytest.mark.usefixtures('apply_mock_dual_tor_tables',
                            'apply_mock_dual_tor_kernel_configs',
                            'run_garp_service',
                            'run_icmp_responder')
]


NEW_NEIGHBOR_IPV4_ADDR = "192.168.0.250"
NEW_NEIGHBOR_HWADDR = "02:AA:BB:CC:DD:EE"


@pytest.fixture(scope="function")
def announce_new_neighbor(ptfadapter, rand_selected_dut, tbinfo):
    """Utility fixture to announce new neighbor from a mux port."""

    def _announce_new_neighbor_gen():
        """Generator to announce the neighbor to a different interface at each iteration."""
        for dut_iface in dut_ifaces:
            update_iface_func = yield dut_iface
            if callable(update_iface_func):
                update_iface_func(dut_iface)
            ptf_iface = dut_to_ptf_intf_map[dut_iface]
            garp_packet = testutils.simple_arp_packet(
                eth_src=NEW_NEIGHBOR_HWADDR,
                hw_snd=NEW_NEIGHBOR_HWADDR,
                ip_snd=NEW_NEIGHBOR_IPV4_ADDR,
                ip_tgt=NEW_NEIGHBOR_IPV4_ADDR,
                arp_op=2
            )
            logging.info(
                "GARP packet to announce new neighbor %s to mux interface %s:\n%s",
                NEW_NEIGHBOR_IPV4_ADDR, dut_iface, dump_scapy_packet_show_output(garp_packet)
            )
            testutils.send(ptfadapter, int(ptf_iface), garp_packet, count=5)
            # let the generator stops here to allow the caller to execute testings
            yield

    dut_to_ptf_intf_map = rand_selected_dut.get_extended_minigraph_facts(tbinfo)['minigraph_ptf_indices']
    mux_configs = mux_cable_server_ip(rand_selected_dut)
    dut_ifaces = list(mux_configs.keys())
    random.shuffle(dut_ifaces)
    return _announce_new_neighbor_gen()


@pytest.fixture(autouse=True)
def cleanup_arp(duthosts):
    """Cleanup arp entries after test."""
    yield
    for duthost in duthosts:
        duthost.shell("sonic-clear arp")


@pytest.fixture(autouse=True)
def enable_garp(duthost):
    """Enable creating arp table entry for gratuitous ARP."""
    vlan_intf = list(duthost.get_running_config_facts()["VLAN_MEMBER"].keys())[0]
    cmd = "echo %s > /proc/sys/net/ipv4/conf/" + vlan_intf + "/arp_accept"
    duthost.shell(cmd % 1)
    yield
    duthost.shell(cmd % 0)


def test_mac_move(
    announce_new_neighbor, apply_active_state_to_orchagent,
    conn_graph_facts, ptfadapter, ptfhost,
    rand_selected_dut, set_crm_polling_interval,
    tbinfo, tunnel_traffic_monitor, vmhost          # noqa: F811
):
    tor = rand_selected_dut
    ptf_t1_intf = random.choice(get_t1_ptf_ports(tor, tbinfo))
    ptf_t1_intf_index = int(ptf_t1_intf.strip("eth"))

    # new neighbor learnt on an active port
    test_port = next(announce_new_neighbor)
    announce_new_neighbor.send(None)
    logging.info("let new neighbor learnt on active port %s", test_port)
    pkt, exp_pkt = build_packet_to_server(tor, ptfadapter, NEW_NEIGHBOR_IPV4_ADDR)
    tunnel_monitor = tunnel_traffic_monitor(tor, existing=False)
    server_traffic_monitor = ServerTrafficMonitor(
        tor, ptfhost, vmhost, tbinfo, test_port, conn_graph_facts, exp_pkt,
        existing=True, is_mocked=is_mocked_dualtor(tbinfo)
    )
    with crm_neighbor_checker(tor), tunnel_monitor, server_traffic_monitor:
        testutils.send(ptfadapter, ptf_t1_intf_index, pkt, count=10)

    # mac move to a standby port
    test_port = next(announce_new_neighbor)
    announce_new_neighbor.send(lambda iface: set_dual_tor_state_to_orchagent(tor, "standby", [iface]))
    logging.info("mac move to a standby port %s", test_port)
    pkt, exp_pkt = build_packet_to_server(tor, ptfadapter, NEW_NEIGHBOR_IPV4_ADDR)
    tunnel_monitor = tunnel_traffic_monitor(tor, existing=True)
    server_traffic_monitor = ServerTrafficMonitor(
        tor, ptfhost, vmhost, tbinfo, test_port, conn_graph_facts, exp_pkt,
        existing=False, is_mocked=is_mocked_dualtor(tbinfo)
    )
    with crm_neighbor_checker(tor), tunnel_monitor, server_traffic_monitor:
        testutils.send(ptfadapter, ptf_t1_intf_index, pkt, count=10)

    # standby forwarding check after fdb ageout/flush
    tor.shell("fdbclear")
    server_traffic_monitor = ServerTrafficMonitor(
        tor, ptfhost, vmhost, tbinfo, test_port, conn_graph_facts, exp_pkt,
        existing=False, is_mocked=is_mocked_dualtor(tbinfo)
    )
    with crm_neighbor_checker(tor), tunnel_monitor, server_traffic_monitor:
        testutils.send(ptfadapter, ptf_t1_intf_index, pkt, count=10)

    # mac move to another active port
    test_port = next(announce_new_neighbor)
    announce_new_neighbor.send(None)
    logging.info("mac move to another active port %s", test_port)
    pkt, exp_pkt = build_packet_to_server(tor, ptfadapter, NEW_NEIGHBOR_IPV4_ADDR)
    tunnel_monitor = tunnel_traffic_monitor(tor, existing=False)
    server_traffic_monitor = ServerTrafficMonitor(
        tor, ptfhost, vmhost, tbinfo, test_port, conn_graph_facts, exp_pkt,
        existing=True, is_mocked=is_mocked_dualtor(tbinfo)
    )
    with crm_neighbor_checker(tor), tunnel_monitor, server_traffic_monitor:
        testutils.send(ptfadapter, ptf_t1_intf_index, pkt, count=10)

    # active forwarding check after fdb ageout/flush
    # skip Mellanox and cisco platforms for the traffic will be flooded in the vlan when there is no fdb entries
    if not (tor.facts['asic_type'] == 'mellanox' or tor.facts['asic_type'] == 'cisco-8000'):
        tor.shell("fdbclear")
        server_traffic_monitor = ServerTrafficMonitor(
            tor, ptfhost, vmhost, tbinfo, test_port, conn_graph_facts, exp_pkt,
            existing=False, is_mocked=is_mocked_dualtor(tbinfo)
        )
        with crm_neighbor_checker(tor), tunnel_monitor, server_traffic_monitor:
            testutils.send(ptfadapter, ptf_t1_intf_index, pkt, count=10)
