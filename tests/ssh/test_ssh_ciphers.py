"""
=============================================================================
Module: ssh
File: test_ssh_ciphers.py
=============================================================================

Description:
    This test file validates SSH security configurations on SONiC devices by verifying
    that only permitted encryption ciphers, MAC algorithms, and key exchange (KEX)
    algorithms are supported. It ensures SSH connections can be established using
    secure cryptographic algorithms and that the SSH protocol version is properly
    configured to only support version 2.x.

Test Intent:
    - test_ssh_protocol_version: Verifies that the SSH daemon only supports protocol
      version 2.x and does not support the insecure version 1.x by checking OpenSSH
      version output.
    - test_ssh_enc_ciphers: Tests SSH connections using each permitted encryption
      cipher (aes256-gcm@openssh.com, aes256-ctr, aes192-ctr) to verify they are
      supported and functional.
    - test_ssh_macs: Tests SSH connections using each permitted MAC algorithm
      (hmac-sha2-512-etm@openssh.com, hmac-sha2-256-etm@openssh.com) to ensure
      message authentication codes work properly.
    - test_ssh_kex: Tests SSH connections using each permitted key exchange algorithm
      (ecdh-sha2-nistp384, ecdh-sha2-nistp521) to validate KEX functionality.

Topology:
    any (works with any topology type)

Fixtures Used:
    - duthosts: Provides access to all DUT hosts in the testbed
    - rand_one_dut_hostname: Randomly selects one DUT hostname for testing
    - enum_dut_ssh_enc_cipher: Parametrized fixture that enumerates all encryption
      ciphers supported by the DUT (generated dynamically via conftest.py)
    - enum_dut_ssh_mac: Parametrized fixture that enumerates all MAC algorithms
      supported by the DUT (generated dynamically via conftest.py)
    - enum_dut_ssh_kex: Parametrized fixture that enumerates all KEX algorithms
      supported by the DUT (generated dynamically via conftest.py)
    - creds: Provides login credentials for accessing the DUT

Dependencies:
    - pexpect: For interactive SSH connection testing
    - pytest: Test framework
    - tests.common.helpers.assertions: For test assertions

Notes:
    - Tests are marked for 'vs' device types and 'any' topology
    - Permitted cipher lists are defined in conftest.py
    - Non-permitted ciphers are marked as xfail in the parametrization
    - Tests support multiple password attempts including alternate passwords
    - The test uses pexpect to simulate interactive SSH sessions with various
      cryptographic options
=============================================================================
"""
import pexpect
import logging
import pytest

from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.device_type('vs')
]


def connect_with_specified_ciphers(duthosts, rand_one_dut_hostname, specified_cipher, creds, typename):
    duthost = duthosts[rand_one_dut_hostname]
    dutuser, dutpass = creds['sonicadmin_user'], creds['sonicadmin_password']
    sonic_admin_alt_password = duthost.host.options['variable_manager']._hostvars[duthost.hostname].get(
        "ansible_altpassword")
    sonic_admin_alt_passwords = creds["ansible_altpasswords"]
    dut_passwords = [dutpass, sonic_admin_alt_password] + sonic_admin_alt_passwords
    dutip = duthost.mgmt_ip

    if typename == "enc":
        ssh_cipher_option = "-c {}".format(specified_cipher)
    elif typename == "mac":
        ssh_cipher_option = "-m {}".format(specified_cipher)
    elif typename == "kex":
        ssh_cipher_option = "-o KexAlgorithms={}".format(specified_cipher)
    else:
        pytest.fail("typename only supports enc/mac/kex")

    ssh_cmd = "ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no {} {}@{}".format(
        ssh_cipher_option, dutuser, dutip)

    for dutpass in dut_passwords:
        try:
            connect = pexpect.spawn(ssh_cmd)
            connect.expect('.*[Pp]assword:')
            connect.sendline(dutpass)

            i = connect.expect(
                '{}@{}:'.format(dutuser, duthost.hostname), timeout=10)
            pytest_assert(i == 0, "Failed to connect")
            return
        except Exception as e:
            output = connect.before.decode()
            if "Permission denied" in output:
                continue
            else:
                pytest.fail(e)
    pytest.fail("Cannot connect to DUT host via SSH")


def test_ssh_protocol_version(duthosts, rand_one_dut_hostname):
    duthost = duthosts[rand_one_dut_hostname]
    result = duthost.shell("sshd --error", module_ignore_errors=True)
    major_version = result["stderr"].split("OpenSSH_", 1)[1].split(".", 1)[0]
    if int(major_version) < 7 or '[-1' in result["stderr"]:
        pytest.fail(
            "SSHD may support protocol version 1.x, only version 2.x will be passed")


def test_ssh_enc_ciphers(duthosts, rand_one_dut_hostname, enum_dut_ssh_enc_cipher, creds):
    typename = "enc"
    connect_with_specified_ciphers(
        duthosts, rand_one_dut_hostname, enum_dut_ssh_enc_cipher, creds, typename)


def test_ssh_macs(duthosts, rand_one_dut_hostname, enum_dut_ssh_mac, creds):
    typename = "mac"
    connect_with_specified_ciphers(
        duthosts, rand_one_dut_hostname, enum_dut_ssh_mac, creds, typename)


def test_ssh_kex(duthosts, rand_one_dut_hostname, enum_dut_ssh_kex, creds):
    typename = "kex"
    connect_with_specified_ciphers(
        duthosts, rand_one_dut_hostname, enum_dut_ssh_kex, creds, typename)
