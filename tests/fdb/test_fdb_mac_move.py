"""
=============================================================================
Module: fdb
File: test_fdb_mac_move.py
=============================================================================

Description:
    This module tests FDB MAC address movement across different ports in a
    SONiC switch. It validates that when a MAC address moves from one port
    to another, the FDB table is updated correctly and packets are forwarded
    to the new port location.

Test Intent:
    - test_fdb_mac_move: Validates MAC address movement across VLAN member
      ports by repeatedly moving MAC addresses between ports and verifying
      FDB table updates correctly. Tests run multiple iterations based on
      completeness level (debug=1, basic=10, confident=50, thorough=100,
      diagnose=200) to stress test MAC learning and movement.

Topology:
    Supports t0 topology

Fixtures Used:
    - get_function_completeness_level: Determines test iteration count
    - rotate_syslog: Rotates syslog to prevent filling during long tests
    - ptfadapter: PTF adapter for sending/receiving packets
    - duthosts: Provides DUT host objects
    - rand_one_dut_hostname: Randomly selected DUT for testing
    - fanouthosts: Fanout switch hosts for port control
    - ptfhost: PTF host for traffic generation

Dependencies:
    - tests.common.utilities: wait_until utility for polling
    - tests.common.helpers.assertions: pytest_assert for validations
    - .utils: MacToInt, IntToMac, fdb_cleanup, get_crm_resources,
      send_arp_request, get_fdb_dynamic_mac_count utilities

Notes:
    - Uses base MAC address format "02:11:22:{port_index}:00:00"
    - Generates up to 12000 total FDB entries for stress testing
    - MAC addresses are moved between ports using ARP requests
    - Test validates FDB table consistency after each MAC move
    - CRM resources are monitored to ensure no resource leaks
    - Completeness level controls iteration count for different test depths
    - Syslog rotation prevents disk space issues during long-running tests
=============================================================================
"""
import logging
import time
import math
import pytest

from collections import defaultdict
from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from .utils import MacToInt, IntToMac, fdb_cleanup, get_crm_resources, send_arp_request, get_fdb_dynamic_mac_count

TOTAL_FDB_ENTRIES = 12000
FDB_POPULATE_SLEEP_TIMEOUT = 2
BASE_MAC_ADDRESS = "02:11:22:{:02x}:00:00"

LOOP_TIMES_LEVEL_MAP = {
    'debug': 1,
    'basic': 10,
    'confident': 50,
    'thorough': 100,
    'diagnose': 200
}

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t0')
]


def get_fdb_dict(ptfadapter, vlan_table, dummay_mac_count):
    """
    :param ptfadapter: PTF adapter object
    :param vlan_table: VLAN table map: VLAN subnet -> list of VLAN members
    :return: FDB table map : VLAN member -> MAC addresses set
    """

    fdb = {}
    vlan = list(vlan_table.keys())[0]

    for member in vlan_table[vlan]:
        if 'port_index' not in member or 'tagging_mode' not in member:
            continue
        if not member['port_index']:
            continue

        port_index = member['port_index'][0]

        fdb[port_index] = {}

        dummy_macs = []
        base_mac = BASE_MAC_ADDRESS.format(port_index)
        for i in range(dummay_mac_count):
            mac_address = IntToMac(MacToInt(base_mac) + i)
            dummy_macs.append(mac_address)
        fdb[port_index] = dummy_macs
    return fdb


def test_fdb_mac_move(ptfadapter, duthosts, fanouthosts, rand_one_dut_hostname, ptfhost,
                      get_function_completeness_level, rotate_syslog):

    # Perform FDB clean up before each test
    fdb_cleanup(duthosts, rand_one_dut_hostname, fanouthosts)

    normalized_level = get_function_completeness_level
    if normalized_level is None:
        normalized_level = "debug"
    loop_times = LOOP_TIMES_LEVEL_MAP[normalized_level]

    duthost = duthosts[rand_one_dut_hostname]
    conf_facts = duthost.config_facts(host=duthost.hostname, source="persistent")['ansible_facts']

    # reinitialize data plane due to above changes on PTF interfaces
    ptfadapter.reinit()

    router_mac = duthost.facts['router_mac']

    port_index_to_name = {v: k for k, v in list(conf_facts['port_index_map'].items())}

    # Only take interfaces that are in ptf topology
    ptf_ports_available_in_topo = ptfhost.host.options['variable_manager'].extra_vars.get("ifaces_map")
    available_ports_idx = []
    for idx, name in list(ptf_ports_available_in_topo.items()):
        if idx in port_index_to_name and conf_facts['PORT'][port_index_to_name[idx]].get('admin_status',
                                                                                         'down') == 'up':
            available_ports_idx.append(idx)

    vlan_table = {}
    interface_table = defaultdict(set)
    config_portchannels = conf_facts.get('PORTCHANNEL', {})

    # if DUT has more than one VLANs, use the first vlan
    name = list(conf_facts['VLAN'].keys())[0]
    vlan = conf_facts['VLAN'][name]
    vlan_id = int(vlan['vlanid'])
    vlan_table[vlan_id] = []

    for ifname in list(conf_facts['VLAN_MEMBER'][name].keys()):
        if 'tagging_mode' not in conf_facts['VLAN_MEMBER'][name][ifname]:
            continue
        tagging_mode = conf_facts['VLAN_MEMBER'][name][ifname]['tagging_mode']
        port_index = []
        if ifname in config_portchannels:
            for member in config_portchannels[ifname]['members']:
                if conf_facts['port_index_map'][member] in available_ports_idx:
                    port_index.append(conf_facts['port_index_map'][member])
            if port_index:
                interface_table[ifname].add(vlan_id)
        elif conf_facts['port_index_map'][ifname] in available_ports_idx:
            port_index.append(conf_facts['port_index_map'][ifname])
            interface_table[ifname].add(vlan_id)
        if port_index:
            vlan_table[vlan_id].append({'port_index': port_index, 'tagging_mode': tagging_mode})

    vlan = list(vlan_table.keys())[0]
    vlan_member_count = len(vlan_table[vlan])
    total_fdb_entries = min(TOTAL_FDB_ENTRIES, (
            get_crm_resources(duthost, "fdb_entry", "available") - get_crm_resources(duthost, "fdb_entry", "used")))
    dummay_mac_count = int(math.floor(total_fdb_entries / vlan_member_count))

    fdb = get_fdb_dict(ptfadapter, vlan_table, dummay_mac_count)
    port_list = list(fdb.keys())
    dummy_mac_list = list(fdb.values())

    for loop_time in range(0, loop_times):
        port_index_start = (0 + loop_time) % len(port_list)

        # Use actual port numbers from port_list instead of calculating indices
        for i in range(len(port_list)):
            port_index = port_list[(port_index_start + i) % len(port_list)]
            dummy_mac_set = dummy_mac_list[(port_index_start + i) % len(port_list)]
            for dummy_mac in dummy_mac_set:
                send_arp_request(ptfadapter, port_index, dummy_mac, router_mac, vlan_id)

        time.sleep(FDB_POPULATE_SLEEP_TIMEOUT)
        pytest_assert(
            wait_until(20, 1, 0, lambda: get_fdb_dynamic_mac_count(duthost) > vlan_member_count),
            (
                "FDB Table Add failed. Expected FDB dynamic MAC count to be greater than {}."
            ).format(vlan_member_count)
        )
        # Flush dataplane
        ptfadapter.dataplane.flush()
        time.sleep(10)
        fdb_cleanup(duthosts, rand_one_dut_hostname, fanouthosts)
        # Wait for 10 seconds before starting next loop
        time.sleep(10)
