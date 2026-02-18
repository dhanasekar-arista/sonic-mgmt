"""
=============================================================================
Module: tacacs
File: test_jit_user.py
=============================================================================

Description:
    This test file validates Just-In-Time (JIT) user provisioning via TACACS+
    authentication. It tests that user privilege levels can be dynamically changed
    on the TACACS server and reflected on the DUT without requiring user recreation,
    allowing seamless role transitions between regular user (netuser) and admin
    user (netadmin) privileges.

Test Intent:
    - test_jit_user: Validates JIT user privilege management by (1) authenticating
      as JIT user with initial netuser privileges and verifying 'test' and
      'remote_user' groups in /etc/passwd, (2) changing JIT user membership to
      netadmin on TACACS server and verifying user now has 'testadmin' and
      'remote_user_su' groups indicating admin privileges, (3) changing membership
      back to netuser and confirming privileges revert to 'test' and 'remote_user'
      groups, proving dynamic privilege changes work without user account recreation.

Topology:
    any, t1-multi-asic (works with multiple topology types)

Fixtures Used:
    - localhost: Local host object for SSH operations
    - duthosts: Provides access to all DUT hosts
    - ptfhost: PTF host for TACACS server setup
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hwsku
    - tacacs_creds: Provides TACACS credentials including JIT user details
    - check_tacacs: Validates TACACS service is running and configured

Dependencies:
    - pytest: Test framework
    - tests.common.helpers.tacacs.tacacs_helper: TACACS helper functions for SSH
      and server configuration
    - tests.common.utilities: Provides check_output helper

Notes:
    - Test is marked to disable log analyzer and work with 'vs' device types
    - JIT user starts with netuser membership (basic privileges)
    - netuser maps to groups: test, remote_user
    - netadmin maps to groups: testadmin, remote_user_su
    - User membership changes are applied via setup_tacacs_server()
    - No user account recreation required when changing privileges
    - Tests seamless privilege escalation and de-escalation
    - Uses SSH to verify group membership in /etc/passwd
=============================================================================
"""
import logging
import pytest
from tests.common.helpers.tacacs.tacacs_helper import ssh_remote_run
from tests.common.helpers.tacacs.tacacs_helper import setup_tacacs_server, check_tacacs  # noqa: F401
from tests.common.utilities import check_output

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology('any', 't1-multi-asic'),
    pytest.mark.device_type('vs')
]

logger = logging.getLogger(__name__)


def test_jit_user(localhost, duthosts, ptfhost, enum_rand_one_per_hwsku_hostname, tacacs_creds,
                  check_tacacs):  # noqa: F811
    """check jit user. netuser -> netadmin -> netuser"""

    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    dutip = duthost.mgmt_ip

    res = ssh_remote_run(localhost, dutip, tacacs_creds['tacacs_jit_user'],
                         tacacs_creds['tacacs_jit_user_passwd'], 'cat /etc/passwd')

    check_output(res, 'test', 'remote_user')

    # change jit user to netadmin
    tacacs_creds['tacacs_jit_user_membership'] = 'netadmin'
    setup_tacacs_server(ptfhost, tacacs_creds, duthost)

    res = ssh_remote_run(localhost, dutip, tacacs_creds['tacacs_jit_user'],
                         tacacs_creds['tacacs_jit_user_passwd'], 'cat /etc/passwd')

    check_output(res, 'testadmin', 'remote_user_su')

    # change jit user back to netuser
    tacacs_creds['tacacs_jit_user_membership'] = 'netuser'
    setup_tacacs_server(ptfhost, tacacs_creds, duthost)

    res = ssh_remote_run(localhost, dutip, tacacs_creds['tacacs_jit_user'],
                         tacacs_creds['tacacs_jit_user_passwd'], 'cat /etc/passwd')
    check_output(res, 'test', 'remote_user')
