"""
=============================================================================
Module: cacl
File: test_cacl_function.py
=============================================================================

Description:
    This functional test validates end-to-end Control Plane ACL (CACL)
    functionality by temporarily applying restrictive ACL rules that block
    SSH, SNMP, and NTP access to verify proper ACL enforcement and restoration.

Test Intent:
    - test_cacl_function: Verifies control plane ACL enforcement by running
      config_service_acls.sh script that temporarily blocks management traffic
      to an unused IP range, confirming that SSH, SNMP, and NTP connections
      are properly rejected during enforcement and restored after the script
      completes its cleanup phase.

Topology:
    any, t1-multi-asic - Test runs on any topology including multi-ASIC
    configurations

Fixtures Used:
    - duthosts: Multi-DUT fixture providing access to all DUT hosts
    - enum_rand_one_per_hwsku_hostname: Randomly selects one DUT per hardware SKU
    - localhost: Ansible localhost fixture for wait_for operations
    - creds: Device credentials including SNMP community strings

Dependencies:
    - pytest: Test framework
    - logging: Python logging module
    - ntplib: NTP client library (optional, warning issued if not installed)
    - tests.common.helpers.assertions: pytest_assert for enhanced error messages
    - tests.common.helpers.snmp_helpers: SNMP fact gathering utilities
    - tests.common.utilities: get_data_acl and recover_acl_rule for ACL management
    - scripts/config_service_acls.sh: Shell script that applies and reverts test ACLs

Notes:
    - Test is restricted to Virtual Switch (vs) device type only
    - Loganalyzer disabled to prevent false positives during ACL changes
    - The config_service_acls.sh script runs in background (nohup) to survive
      SSH session termination
    - Script automatically reverts ACL changes after ~3 minutes
    - SSH connection is expected to fail during restrictive ACL period
    - SNMP and NTP services should timeout when ACLs are restrictive
    - For chassis-packet devices, SNMP timeout is reduced to 5 seconds
    - Total test duration includes 210-second timeout for ACL restoration
    - Data ACL rules are recovered at test completion to restore original state
    - Test validates three phases: initial access, blocked access, restored access
=============================================================================
"""

import pytest
import logging
from tests.common.helpers.assertions import pytest_assert
from tests.common.helpers.snmp_helpers import get_snmp_facts, SNMP_DEFAULT_TIMEOUT
from tests.common.utilities import get_data_acl, recover_acl_rule

try:
    import ntplib
    NTPLIB_INSTALLED = True
except ImportError:
    NTPLIB_INSTALLED = False

pytestmark = [
    pytest.mark.disable_loganalyzer,  # disable automatic loganalyzer globally
    pytest.mark.topology('any', 't1-multi-asic'),
    pytest.mark.device_type('vs')
]

SONIC_SSH_PORT = 22
SONIC_SSH_REGEX = 'OpenSSH_[\\w\\.]+ Debian'


def test_cacl_function(duthosts, enum_rand_one_per_hwsku_hostname, localhost, creds):
    """Test control plane ACL functionality on a SONiC device"""

    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    data_acl = get_data_acl(duthost)
    dut_mgmt_ip = duthost.mgmt_ip

    # Start an NTP client
    if NTPLIB_INSTALLED:
        ntp_client = ntplib.NTPClient()
    else:
        logging.warning("Will not check NTP connection. ntplib is not installed.")

    # Ensure we can gather basic SNMP facts from the device. Should fail on timeout
    get_snmp_facts(duthost,
                   localhost,
                   host=dut_mgmt_ip,
                   version="v2c",
                   community=creds['snmp_rocommunity'],
                   wait=True,
                   timeout=30,
                   interval=5)

    # Ensure we can send an NTP request
    if NTPLIB_INSTALLED:
        try:
            ntp_client.request(dut_mgmt_ip)
        except ntplib.NTPException:
            pytest.fail("NTP did timed out when expected to succeed!")
    try:
        # Copy config_service_acls.sh to the DuT (this also implicitly verifies we can successfully SSH to the DuT)
        duthost.copy(src="scripts/config_service_acls.sh", dest="/tmp/config_service_acls.sh", mode="0755")

        # We run the config_service_acls.sh script in the background because it
        # will install ACL rules which will only allow control plane traffic
        # to an unused IP range. Thus, if it works properly, it will sever our
        # SSH session, but we don't want the script itself to get killed,
        # because it is also responsible for resetting the control plane ACLs
        # back to their previous, working state
        duthost.shell("nohup /tmp/config_service_acls.sh < /dev/null > /dev/null 2>&1 &")

        # Wait until we are unable to SSH into the DuT
        res = localhost.wait_for(host=dut_mgmt_ip,
                                 port=SONIC_SSH_PORT,
                                 state='stopped',
                                 search_regex=SONIC_SSH_REGEX,
                                 delay=30,
                                 timeout=40,
                                 module_ignore_errors=True)

        pytest_assert(not res.is_failed, "SSH port did not stop. {}".format(res.get('msg', '')))

        # Try to SSH back into the DuT, it should time out
        res = localhost.wait_for(host=dut_mgmt_ip,
                                 port=SONIC_SSH_PORT,
                                 state='started',
                                 search_regex=SONIC_SSH_REGEX,
                                 delay=0,
                                 timeout=10,
                                 module_ignore_errors=True)

        pytest_assert(res.is_failed, "SSH did not timeout when expected. {}".format(res.get('msg', '')))

        snmp_timeout = SNMP_DEFAULT_TIMEOUT
        if duthost.facts['switch_type'] == "chassis-packet":
            snmp_timeout = 5
        # Ensure we CANNOT gather basic SNMP facts from the device
        res = get_snmp_facts(duthost, localhost, host=dut_mgmt_ip, version='v2c', community=creds['snmp_rocommunity'],
                             module_ignore_errors=True, snmp_timeout=snmp_timeout)

        pytest_assert('ansible_facts' not in res and "No SNMP response received before timeout" in res.get('msg', ''))

        # Ensure we cannot send an NTP request to the DUT
        if NTPLIB_INSTALLED:
            try:
                ntp_client.request(dut_mgmt_ip)
                pytest.fail("NTP did not time out when expected")
            except ntplib.NTPException:
                pass

        # Wait until the original service ACLs are reinstated and the SSH port on the
        # DUT is open to us once again. Note that the timeout here should be set sufficiently
        # long enough to allow config_service_acls.sh to reset the ACLs to their original
        # configuration.
        res = localhost.wait_for(host=dut_mgmt_ip,
                                 port=SONIC_SSH_PORT,
                                 state='started',
                                 search_regex=SONIC_SSH_REGEX,
                                 delay=0,
                                 timeout=210,
                                 module_ignore_errors=True)

        pytest_assert(not res.is_failed, "SSH did not start working when expected. {}".format(res.get('msg', '')))

        # Delete config_service_acls.sh from the DuT
        duthost.file(path="/tmp/config_service_acls.sh", state="absent")

        # Ensure we can gather basic SNMP facts from the device once again. Should fail on timeout
        get_snmp_facts(duthost,
                       localhost,
                       host=dut_mgmt_ip,
                       version="v2c",
                       community=creds['snmp_rocommunity'],
                       wait=True,
                       timeout=120,
                       interval=20)
    finally:
        if data_acl:
            recover_acl_rule(duthost, data_acl)
