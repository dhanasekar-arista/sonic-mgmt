"""
=============================================================================
Module: snmp
File: test_snmp_v2mib.py
=============================================================================

Description:
    This test module validates SNMPv2-MIB standard objects on SONiC switches,
    verifying system identification MIB variables (sysName, sysDescr, sysLocation,
    sysContact) are correctly populated and accessible via SNMP v2c queries.

Test Intent:
    - test_snmp_v2mib: Validates SNMPv2-MIB system group objects by verifying
      sysName matches hostname, sysLocation matches snmp.yml configuration,
      sysContact matches snmpd.conf setting, and sysDescr contains expected
      system information (kernel version, HWSKU, SONiC OS version, Debian version)

Topology:
    - Supported: any topology
    - Works across all device types and configurations

Fixtures Used:
    - duthosts: All DUT hosts in testbed
    - enum_rand_one_per_hwsku_hostname: Randomly selected DUT for testing
    - localhost: Local connection for SNMP queries
    - creds_all_duts: SNMP community string credentials

Dependencies:
    - tests.common.helpers.snmp_helpers: SNMP fact gathering via snmpwalk
    - SNMPv2-MIB: Standard SNMP system group (RFC 3418)

Notes:
    - SNMP version: v2c (community-based)
    - MIB objects tested:
      - sysName (1.3.6.1.2.1.1.5): System hostname
      - sysDescr (1.3.6.1.2.1.1.1): System description with OS details
      - sysLocation (1.3.6.1.2.1.1.6): Physical location from snmp.yml
      - sysContact (1.3.6.1.2.1.1.4): Admin contact from snmpd.conf
    - sysContact extracted from /etc/snmp/snmpd.conf in snmp container
    - sysLocation extracted from /etc/sonic/snmp.yml configuration
    - sysDescr validation includes: kernel version, HWSKU, SONiC OS version, Debian version
    - Debian version read from /etc/debian_version
    - All system values must be present in sysDescr string
=============================================================================
"""

import pytest
from tests.common.helpers.assertions import pytest_assert  # pylint: disable=import-error
from tests.common.helpers.snmp_helpers import get_snmp_facts

pytestmark = [
    pytest.mark.topology('any')
]


def test_snmp_v2mib(duthosts, enum_rand_one_per_hwsku_hostname, localhost, creds_all_duts):
    """
    Verify SNMPv2-MIB objects are functioning properly
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    host_ip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']
    snmp_facts = get_snmp_facts(
        duthost, localhost, host=host_ip, version="v2c",
        community=creds_all_duts[duthost.hostname]["snmp_rocommunity"], wait=True)['ansible_facts']
    dut_facts = duthost.setup()['ansible_facts']
    debian_ver = duthost.shell('cat /etc/debian_version')['stdout']
    cmd = 'docker exec snmp grep "sysContact" /etc/snmp/snmpd.conf'
    sys_contact = " ".join(duthost.shell(cmd)['stdout'].split()[1:])
    sys_location = duthost.shell(
        "grep 'snmp_location' /etc/sonic/snmp.yml")['stdout'].split()[-1]

    expected_res = {'kernel_version': dut_facts['ansible_kernel'],
                    'hwsku': duthost.facts['hwsku'],
                    'os_version': 'SONiC.{}'.format(duthost.os_version),
                    'debian_version': '{} {}'.format(dut_facts['ansible_distribution'], debian_ver)}

    # Verify that sysName, sysLocation and sysContact MIB objects functions properly
    pytest_assert(snmp_facts['ansible_sysname'] == duthost.hostname,
                  "Unexpected MIB result {}".format(snmp_facts['ansible_sysname']))
    pytest_assert(snmp_facts['ansible_syslocation'] == sys_location,
                  "Unexpected MIB result {}".format(snmp_facts['ansible_syslocation']))
    pytest_assert(snmp_facts['ansible_syscontact'] == sys_contact,
                  "Unexpected MIB result {}".format(snmp_facts['ansible_syscontact']))

    # Verify that sysDescr MIB object functions properly
    missed_values = []
    for system_value in expected_res:
        if expected_res[system_value] not in snmp_facts['ansible_sysdescr']:
            missed_values.append(expected_res[system_value])
    pytest_assert(not missed_values, "System values {} was not found in SNMP facts: {}"
                  .format(missed_values, snmp_facts['ansible_sysdescr']))
