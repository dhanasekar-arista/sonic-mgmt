"""
=============================================================================
Module: tacacs
File: test_rw_user.py
=============================================================================

Description:
    This test file validates read-write (RW) user permissions via TACACS+
    authentication. It ensures that RW users (admin-level users) are properly
    authenticated and assigned to the correct admin groups with full sudo privileges,
    supporting both IPv4 and IPv6 TACACS servers.

Test Intent:
    - test_rw_user: Validates TACACS RW user authentication and group membership
      via IPv4 TACACS server by executing 'cat /etc/passwd' and verifying the user
      is assigned to 'testadmin' and 'remote_user_su' groups, confirming admin
      privileges are correctly granted.
    - test_rw_user_ipv6: Validates TACACS RW user authentication and group membership
      via IPv6 TACACS server by executing 'cat /etc/passwd' and verifying the user
      is assigned to 'testadmin' and 'remote_user_su' groups, confirming IPv6
      TACACS support works correctly for admin users.

Topology:
    any, t1-multi-asic (works with multiple topology types)

Fixtures Used:
    - localhost: Local host object for SSH operations
    - duthosts: Provides access to all DUT hosts
    - ptfhost: PTF host for IPv6 TACACS server testing
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hwsku
    - tacacs_creds: Provides TACACS credentials including RW user details
    - check_tacacs: Validates TACACS service is running (IPv4)
    - check_tacacs_v6: Validates IPv6 TACACS service is running

Dependencies:
    - pytest: Test framework
    - tests.common.helpers.tacacs.tacacs_helper: TACACS helper functions for SSH
      operations and server configuration
    - tests.common.utilities: Provides check_output helper for verifying command results

Notes:
    - Test is marked to disable log analyzer and work with 'vs' device types
    - RW user maps to admin groups: testadmin, remote_user_su
    - testadmin group provides full administrative access
    - remote_user_su group grants sudo privileges
    - Uses ssh_remote_run for IPv4 TACACS testing
    - Uses ssh_remote_run_retry for IPv6 TACACS testing with retry logic
    - Tests verify group membership by checking /etc/passwd output
    - RW users have full read-write access to configuration and system commands
=============================================================================
"""
import pytest

from tests.common.helpers.tacacs.tacacs_helper import ssh_remote_run, ssh_remote_run_retry, check_tacacs  # noqa: F401
from tests.common.utilities import check_output

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology('any', 't1-multi-asic'),
    pytest.mark.device_type('vs')
]


def test_rw_user(localhost, duthosts, enum_rand_one_per_hwsku_hostname, tacacs_creds, check_tacacs):  # noqa: F811
    """test tacacs rw user
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    dutip = duthost.mgmt_ip
    res = ssh_remote_run(localhost, dutip, tacacs_creds['tacacs_rw_user'],
                         tacacs_creds['tacacs_rw_user_passwd'], "cat /etc/passwd")

    check_output(res, 'testadmin', 'remote_user_su')


def test_rw_user_ipv6(localhost, duthosts, ptfhost, enum_rand_one_per_hwsku_hostname,
                      tacacs_creds, check_tacacs_v6):
    """test tacacs rw user
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    dutip = duthost.mgmt_ip
    res = ssh_remote_run_retry(localhost, dutip, ptfhost,
                               tacacs_creds['tacacs_rw_user'],
                               tacacs_creds['tacacs_rw_user_passwd'],
                               "cat /etc/passwd")

    check_output(res, 'testadmin', 'remote_user_su')
