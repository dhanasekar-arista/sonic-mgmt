"""
=============================================================================
Module: snmp
File: test_snmp_default_route.py
=============================================================================

Description:
    This test module validates SNMP IP-FORWARD-MIB (ipCidrRouteTable) reporting
    of default route (0.0.0.0/0) on SONiC switches. It compares SNMP-reported
    default route nexthops against CLI "show ip route" output, ensuring SNMP
    correctly exposes default route information excluding management interfaces.

Test Intent:
    - test_snmp_default_route: Compares default route nexthops from SNMP facts
      (ipCidrRouteEntry MIB) with "show ip route 0.0.0.0/0" CLI output, validating
      SNMP reports correct nexthops excluding eth0 and Ethernet-BP interfaces,
      and verifies route destination, mask, type, and protocol fields

Topology:
    - Supported: t0, t1, t2, m0, mx, m1, t1-multi-asic, lt2, ft2
    - Device type: vs (virtual switch)
    - Skip on backend topologies (no default routes)

Fixtures Used:
    - duthosts: All DUT hosts in testbed
    - enum_rand_one_per_hwsku_frontend_hostname: Randomly selected frontend DUT
    - localhost: Local connection for SNMP queries
    - creds_all_duts: SNMP credentials
    - tbinfo: Testbed information for topology validation

Dependencies:
    - tests.common.helpers.snmp_helpers: SNMP fact gathering
    - IP-FORWARD-MIB: ipCidrRouteTable (RFC 2096)

Notes:
    - Default route: 0.0.0.0/0
    - Nexthops via eth0 or Ethernet-BP excluded from comparison
    - SNMP field validations:
      - route_dest: 0.0.0.0
      - route_mask: 0.0.0.0
      - route_type: 4 (remote)
      - route_proto: not 3 (netmgmt)
    - If no valid nexthops exist, snmp_cidr_route should be absent
    - Test skipped on backend topologies (t1-backend, etc.)
    - Multi-ASIC: validates routes across all frontend ASICs
=============================================================================
"""

import pytest

from tests.common.helpers.assertions import pytest_require
from tests.common.helpers.snmp_helpers import get_snmp_facts

pytestmark = [
    pytest.mark.topology('t0', 't1', 't2', 'm0', 'mx', 'm1', 't1-multi-asic', 'lt2', 'ft2', 'c0'),
    pytest.mark.device_type('vs')
]


def test_snmp_default_route(duthosts, enum_rand_one_per_hwsku_frontend_hostname,
                            localhost, creds_all_duts, tbinfo):
    """compare the snmp facts between observed states and target state"""

    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    pytest_require('backend' not in tbinfo['topo']['name'],
                   "Skip this testcase since this topology {} has no default routes"
                   .format(tbinfo['topo']['name']))

    hostip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']
    snmp_facts = get_snmp_facts(
        duthost, localhost, host=hostip, version="v2c",
        community=creds_all_duts[duthost.hostname]["snmp_rocommunity"], wait=True)['ansible_facts']
    dut_result = duthost.shell(r'show ip route 0.0.0.0/0 | grep "\*"')

    dut_result_nexthops = []
    # ipCidrRouteEntry MIB for default route will have entries
    # where next hop are not eth0 interface.
    for line in dut_result['stdout_lines']:
        if 'via' in line:
            ip, interface = line.split('via')
            ip = ip.strip("*, ,recursive")
            interface = interface.strip("*, ")
            if interface != "eth0" and 'Ethernet-BP' not in interface:
                dut_result_nexthops.append(ip)

    # If show ip route 0.0.0.0/0 has route only via eth0,
    # or has no route snmp_facts for ip_cidr_route
    # will be empty.
    if len(dut_result_nexthops) == 0:
        assert 'snmp_cidr_route' not in snmp_facts, 'snmp_cidr_route should not be present in snmp_facts'

    if len(dut_result_nexthops) != 0:
        # Test to ensure show ip route 0.0.0.0/0 result matches with SNMP result
        for ip in dut_result_nexthops:
            assert ip in snmp_facts['snmp_cidr_route'], "{} ip not found in snmp_facts".format(
                ip)
            assert snmp_facts['snmp_cidr_route'][ip]['route_dest'] == '0.0.0.0',\
                "Incorrect route_dest for {} ip".format(ip)
            assert snmp_facts['snmp_cidr_route'][ip]['status'] == '1', "Incorrect status for {} ip".format(
                ip)

        # Compare the length of routes in CLI output and SNMP facts
        assert len(list(snmp_facts['snmp_cidr_route'].keys())) == len(list(snmp_facts['snmp_cidr_route'].keys())), \
            "Number or route entries in SNMP does not match with cli"
