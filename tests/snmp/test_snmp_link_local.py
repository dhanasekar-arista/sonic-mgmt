"""
=============================================================================
Module: snmp
File: test_snmp_link_local.py
=============================================================================

Description:
    This test module validates SNMP functionality over IPv6 link-local addresses
    on SONiC switches. It configures eth0's link-local IP as snmpagentaddress,
    performs SNMP queries over the link-local address from within the SNMP
    docker container, and verifies successful retrieval of system description.

Test Intent:
    - test_snmp_link_local_ip: Configures SNMP agent to listen on eth0 link-local
      IPv6 address, performs SNMP query using link-local IP from SNMP container,
      validates sysDescr retrieval, and ensures SNMP agent binds to link-local
      address correctly

Topology:
    - Supported: t0, t1, t2, m0, mx, m1, t1-multi-asic, lt2, ft2
    - Device type: vs (virtual switch)

Fixtures Used:
    - duthosts: All DUT hosts in testbed
    - enum_rand_one_per_hwsku_frontend_hostname: Randomly selected frontend DUT
    - nbrhosts: Neighbor hosts
    - tbinfo: Testbed information
    - localhost: Local connection
    - creds_all_duts: SNMP credentials
    - config_reload_after_test: Auto-use module fixture performing config reload
      after test completion

Dependencies:
    - tests.common.helpers.snmp_helpers: SNMP fact gathering
    - tests.common.config_reload: Configuration reload utilities
    - IPv6 link-local address discovery on eth0 interface

Notes:
    - Link-local IP extracted from eth0 interface (fe80::/10 prefix)
    - SNMP agent address configured via CONFIG_DB SNMP|LOCATION
    - Config reload performed after test to restore original configuration
    - SNMP LLDP readiness check after config reload (300 second timeout)
    - SNMP query executed from within snmp docker container
    - Validates snmpagent listening on link-local IP via ss command
    - Uses zone ID syntax for link-local addressing (e.g., fe80::1%eth0)
=============================================================================
"""

import pytest
from tests.common.helpers.snmp_helpers import get_snmp_facts
from tests.common import config_reload
from tests.common.utilities import wait_until

pytestmark = [
    pytest.mark.topology('t0', 't1', 't2', 'm0', 'mx', 'm1', 't1-multi-asic', 'lt2', 'ft2', 'c0'),
    pytest.mark.device_type('vs')
]


@pytest.fixture(autouse=True, scope='module')
def config_reload_after_test(duthosts, localhost, creds_all_duts,
                             enum_rand_one_per_hwsku_frontend_hostname):
    yield
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    config_reload(duthost, config_source='config_db', safe_reload=True, check_intf_up_ports=True)

    hostip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']

    # SNMP LLDP takes longer to be ready after config_reload
    def check_snmp_lldp_ready():
        snmp_facts = get_snmp_facts(
            duthost, localhost, host=hostip, version="v2c",
            community=creds_all_duts[duthost.hostname]["snmp_rocommunity"],
            wait=True)['ansible_facts']
        return "No Such Instance currently exists" not in str(snmp_facts['snmp_lldp'])

    if not wait_until(300, 5, 0, check_snmp_lldp_ready):
        pytest.fail("SNMP LLDP not ready for next test")


def is_snmpagent_listen_on_ip(duthost, ipaddr):
    """
    Check if snmpagent is listening on the specific IP address.
    """
    output = duthost.shell('sudo ss -tunlp | grep snmpd', module_ignore_errors=True)['stdout_lines']
    return any([ipaddr in x for x in output])


@pytest.mark.bsl
def test_snmp_link_local_ip(duthosts,
                            enum_rand_one_per_hwsku_frontend_hostname,
                            nbrhosts, tbinfo, localhost, creds_all_duts):
    """
    Test SNMP query to DUT over link local IP
      - configure eth0's link local IP as snmpagentaddress
      - Query over linklocal IP from within snmp docker
      - Get SysDescr from snmpfacts
      - compare result from snmp query over link local IP and snmpfacts
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    hostip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']
    snmp_facts = get_snmp_facts(
        duthost, localhost, host=hostip, version="v2c",
        community=creds_all_duts[duthost.hostname]["snmp_rocommunity"],
        wait=True)['ansible_facts']
    # Get link local IP of mamangement interface
    ip_cmd = 'ip addr show eth0 | grep "inet6" | grep "link"\
              | awk "{print $2}" | cut -d/ -f1'
    link_local_ips = duthost.shell(ip_cmd)['stdout_lines']
    sysdescr_oid = '1.3.6.1.2.1.1.1.0'
    # configure link local IP in config_db
    for ip in link_local_ips:
        if ip.split()[1].lower().startswith('fe80'):
            link_local_ip = ip.split()[1]
            break
    # configure link local IP in config_db
    # Restart snmp service to regenerate snmpd.conf with
    # link local IP configured in MGMT_INTERFACE
    duthost.shell("config snmpagentaddress add {}%eth0".format(link_local_ip))
    if not wait_until(60, 5, 0, is_snmpagent_listen_on_ip, duthost, link_local_ip):
        pytest.fail("SNMP agent not listen on link local IP {}".format(link_local_ip))
    stdout_lines = duthost.shell("docker exec snmp snmpget \
                                 -v2c -c {} {}%eth0 {}"
                                 .format(creds_all_duts[duthost.hostname]
                                         ['snmp_rocommunity'],
                                         link_local_ip,
                                         sysdescr_oid))['stdout_lines'][0]
    assert "SONiC Software Version" in stdout_lines,\
        "Sysdescr not found in SNMP result from Link Local IP {}".format(
                link_local_ip)
    assert snmp_facts['ansible_sysdescr'] in stdout_lines,\
        "Sysdescr from IP{} not matching with result from Mgmt IPv4.".format(
                link_local_ip)
