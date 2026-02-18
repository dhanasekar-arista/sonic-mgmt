"""
=============================================================================
Module: ixia/ixanvl
File: test_bgp_conformance.py
=============================================================================

Description:
    This test module runs IXIA ANVL (Automated Network Validation Library)
    BGP conformance tests on SONiC switches. It executes BGP protocol conformance
    testing using IXIA's ANVL tool running on PTF host.

Test Intent:
    - test_anvl_bgp_run: Executes IXIA ANVL BGP4 conformance test suite or
      specific test cases to validate BGP protocol implementation compliance

Topology:
    - tgen: Requires IXIA traffic generator topology

Fixtures Used:
    - ptfhost: PTF host where IXIA ANVL container runs
    - testnum: Optional test number to run specific ANVL test case

Dependencies:
    - paramiko: SSH client for remote command execution
    - scp: Secure copy for file transfer from ANVL container
    - IXIA ANVL: BGP conformance testing tool

Notes:
    - Log analyzer is disabled for this test
    - Test connects to IXIA ANVL container running on PTF
    - Can run full BGP test suite or specific test case via --testnum option
    - Results are logged to bgp4.log and transferred back via SCP
    - Requires ANVL installed at /opt/Ixia/IxANVL on PTF
=============================================================================
"""
import logging
import paramiko
import pytest

from tests.common.fixtures.conn_graph_facts import conn_graph_facts     # noqa: F401
from scp import SCPClient

pytestmark = [
    pytest.mark.topology('tgen'),
    pytest.mark.disable_loganalyzer
]


@pytest.fixture()
def testnum(pytestconfig):
    return pytestconfig.getoption("testnum")


def test_anvl_bgp_run(ptfhost, testnum):
    """
    1. ANVL run.
    """

    ptfip = ptfhost.host.options['inventory_manager'].get_host(ptfhost.hostname).vars['ansible_host']

    ptfuser = ptfhost.host.options['inventory_manager'].get_host(ptfhost.hostname).vars['ansible_user']
    ptfpass = ptfhost.host.options['inventory_manager'].get_host(ptfhost.hostname).vars['ansible_password']

    logging.info("ixanvl container ip=%s" % ptfip)
    logging.info("ixanvl container ip=%s" % ptfuser)
    logging.info("ixanvl container ip=%s" % ptfpass)

    testnumber = testnum
    logging.info("run anvl with static configuration")
    ixanvl_tester = paramiko.SSHClient()
    # Add missing client key
    ixanvl_tester.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # connect to ptf
    ixanvl_tester.connect(ptfip, username=ptfuser, password=ptfpass)
    logging.info("SSH connection to %s established" % ptfip)

    scp = SCPClient(ixanvl_tester.get_transport())

    # Gather commands and read the output from stdout
    if not testnumber:
        logging.info("================= Running ANVL BGP Full Suite ===============\n")
        command_str = "cd /opt/Ixia/IxANVL && ./anvl -l l -f DocUser/anvlbgp4 bgp4 | tee bgp4.log\n"
    else:
        logging.info("================= Running ANVL BGP Test Case %s ===============\n" % testnumber)
        command_str = "cd /opt/Ixia/IxANVL && ./anvl -l l -f DocUser/anvlbgp4 bgp4 " + testnumber + " | tee bgp4.log\n"

    stdin, stdout, stderr = ixanvl_tester.exec_command(command_str)

    for line in stdout:
        logging.info(line)

    stdout.channel.recv_exit_status()
    scp.get('/opt/Ixia/IxANVL/bgp4.log')

    ixanvl_tester.close()
