"""
=============================================================================
Module: ssh
File: test_ssh_limit.py
=============================================================================

Description:
    This test file validates SSH session limit functionality on SONiC devices by
    testing the PAM (Pluggable Authentication Modules) limits configuration. It verifies
    that template files for pam_limits and limits.conf are correctly rendered by hostcfgd
    and that SSH login session limits are enforced properly to prevent excessive
    concurrent logins from the same user.

Test Intent:
    - test_ssh_limits: Validates two critical scenarios - (1) ensures that the PAM
      limit templates (pam_limits.j2 and limits.conf.j2) are correctly rendered by
      hostcfgd, and (2) verifies that SSH login session limits work correctly by
      testing that a first login succeeds while a second concurrent login from the
      same user is properly rejected with "too many logins" message.

Topology:
    any (works with any topology type)

Fixtures Used:
    - duthosts: Provides access to all DUT hosts in the testbed
    - rand_one_dut_hostname: Randomly selects one DUT hostname for testing
    - tacacs_creds: Provides TACACS credentials including local user credentials
    - setup_limit: Module-scoped fixture that sets up SSH limit testing by modifying
      PAM templates, creating a local user, disabling AAA authentication if needed,
      and restoring configuration after tests complete

Dependencies:
    - json: For parsing device configuration database
    - pytest: Test framework
    - paramiko: For creating multiple SSH sessions
    - tests.common.helpers.assertions: For test assertions
    - tests.common.helpers.tacacs.tacacs_helper: For setting up local users
    - tests.common.utilities: For paramiko_ssh utility function

Notes:
    - Tests are marked to disable log analyzer and work with 'vs' device types
    - Template paths: /usr/share/sonic/templates/pam_limits.j2 and limits.conf.j2
    - The test handles different PAM versions (1.7.0+ requires one extra login slot)
    - If AAA authentication is enabled, it's temporarily disabled for local user login
    - The test skips if the limits.conf.j2 template doesn't exist on the DUT
    - Uses a 10-second timeout for reading login messages from SSH sessions
    - Sonic OS version 13+ (Debian Trixie) requires maxlogins=2 due to systemd-logind
=============================================================================
"""
import json
import logging
import pytest
import time
from tests.common.helpers.assertions import pytest_assert, pytest_require
from tests.common.fixtures.tacacs import tacacs_creds     # noqa F401
from tests.common.helpers.tacacs.tacacs_helper import setup_local_user
from tests.common.utilities import paramiko_ssh
from tests.common.fixtures.tacacs import get_aaa_sub_options_value

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology("any"),
    pytest.mark.device_type("vs"),
]

HOSTSERVICE_RELOADING_COMMAND = "sudo systemctl restart hostcfgd.service"
HOSTSERVICE_RELOADING_TIME = 5

LOGIN_MESSAGE_TIMEOUT = 10
LOGIN_MESSAGE_BUFFER_SIZE = 1000

TEMPLATE_BACKUP_COMMAND = "sudo mv {0} {0}.backup"
TEMPLATE_RESTORE_COMMAND = "sudo mv {0}.backup {0}"
TEMPLATE_CREATE_COMMAND = "sudo touch {0}"

PAM_LIMITS_TEMPLATE_PATH = "/usr/share/sonic/templates/pam_limits.j2"
LIMITS_CONF_TEMPLATE_PATH = "/usr/share/sonic/templates/limits.conf.j2"
LIMITS_CONF_TEMPLATE_TO_HOME = \
    "echo \"{{% if hwsku == '{0}' and type == '{1}'%}}\n{2}\n{{% endif %}}\"  > ~/temp_config_file"
TEMPLATE_MOVE_COMMAND = "sudo mv ~/temp_config_file {0}"


def get_device_type(duthost):
    device_config_db = json.loads(duthost.shell(
        "sonic-cfggen -d --print-data")['stdout'])
    dut_type = None

    if "DEVICE_METADATA" in device_config_db and \
        "localhost" in device_config_db["DEVICE_METADATA"] and \
            "type" in device_config_db["DEVICE_METADATA"]["localhost"]:
        dut_type = device_config_db["DEVICE_METADATA"]["localhost"]["type"]

    return dut_type


def exec_command(admin_session, command):
    stdin, stdout, stderr = admin_session.exec_command(command)
    outstr = stdout.readlines()
    errstr = stderr.readlines()
    logging.info("Command: '{}' stdout: {} stderr: {}".format(command, outstr, errstr))


def modify_template(admin_session, template_path, additional_content, hwsku, type):
    exec_command(admin_session, TEMPLATE_BACKUP_COMMAND.format(template_path))
    exec_command(admin_session, TEMPLATE_CREATE_COMMAND.format(template_path))
    exec_command(admin_session, LIMITS_CONF_TEMPLATE_TO_HOME.format(hwsku, type, additional_content))
    exec_command(admin_session, TEMPLATE_MOVE_COMMAND.format(template_path))
    exec_command(admin_session, 'sudo cat {0}'.format(template_path))


def modify_templates(duthost, tacacs_creds, creds):     # noqa F811
    dut_ip = duthost.mgmt_ip
    hwsku = duthost.facts["hwsku"]
    type = get_device_type(duthost)
    user = tacacs_creds['local_user']

    sonic_admin_alt_password = duthost.host.options['variable_manager']._hostvars[duthost.hostname].get(
        "ansible_altpassword")
    # Duthost shell not support run command with J2 template in command text.
    admin_session = paramiko_ssh(ip_address=dut_ip, username=creds['sonicadmin_user'],
                                 passwords=[creds['sonicadmin_password'], sonic_admin_alt_password]
                                 + creds["ansible_altpasswords"])

    # Backup and change /usr/share/sonic/templates/pam_limits.j2
    additional_content = "session  required  pam_limits.so"
    modify_template(admin_session, PAM_LIMITS_TEMPLATE_PATH,
                    additional_content, hwsku, type)

    # Backup and change /usr/share/sonic/templates/limits.conf.j2

    # Starting with PAM 1.7.0 (present in Debian Trixie and newer), the
    # pam_limits module is relying on systemd-logind for limiting logins.
    # However, one of the sessions is used as a systemd manager session,
    # so the actual count needs to be one higher. This is described a bit
    # in the commit below:
    #
    # https://github.com/linux-pam/linux-pam/commit/f5db2603d2ce80a610a247e06bdd49c4eb091a7d#diff-f454153035e14468d4263c7bc9b85ec0e192be1d16080b65ae4974a74846de25R282-R288
    if duthost.dut_basic_facts()['ansible_facts']['dut_basic_facts'].get("sonic_os_version") >= 13:
        additional_content = "{0}  hard  maxlogins  2".format(user)
    else:
        additional_content = "{0}  hard  maxlogins  1".format(user)
    modify_template(admin_session, LIMITS_CONF_TEMPLATE_PATH,
                    additional_content, hwsku, type)


def restore_templates(duthost):
    duthost.shell(TEMPLATE_RESTORE_COMMAND.format(PAM_LIMITS_TEMPLATE_PATH))
    duthost.shell(TEMPLATE_RESTORE_COMMAND.format(LIMITS_CONF_TEMPLATE_PATH))


def restart_hostcfgd(duthost):
    duthost.shell(HOSTSERVICE_RELOADING_COMMAND)
    time.sleep(HOSTSERVICE_RELOADING_TIME)


def limit_template_exist(duthost):
    return duthost.stat(path=LIMITS_CONF_TEMPLATE_PATH).get('stat', {}).get('exists', False)


@pytest.fixture(scope="module")
def setup_limit(duthosts, rand_one_dut_hostname, tacacs_creds, creds):      # noqa F811
    duthost = duthosts[rand_one_dut_hostname]

    # if template file not exist on duthost, ignore this UT
    # However still need yield, if not yield, UT will failed with StopIteration error.
    template_file_exist = limit_template_exist(duthost)
    aaa_login_disabled = False
    if template_file_exist:
        # If AAA authentication enabled, disable it to allow local user login
        if get_aaa_sub_options_value(duthost, "authentication", "login") == "tacacs+":
            duthost.shell("sudo config aaa authentication login default")
            aaa_login_disabled = True

        setup_local_user(duthost, tacacs_creds)

        # Modify templates and restart hostcfgd to render config files
        modify_templates(duthost, tacacs_creds, creds)
        restart_hostcfgd(duthost)

    yield

    if template_file_exist:
        if aaa_login_disabled:
            duthost.shell("sudo config aaa authentication login tacacs+")

        # Restore SSH session limit
        restore_templates(duthost)
        restart_hostcfgd(duthost)


def get_login_result(ssh_session):
    login_channel = ssh_session.invoke_shell()
    login_message = ""
    start_time = time.time()
    while (time.time() - start_time) <= LOGIN_MESSAGE_TIMEOUT:
        if login_channel.recv_ready():
            data = login_channel.recv(LOGIN_MESSAGE_BUFFER_SIZE)
            if len(data) == 0:
                # when receive zero length data, channel closed
                break
            login_message += data.decode("utf-8")

        time.sleep(1)

    return login_message


def test_ssh_limits(duthosts, rand_one_dut_hostname, tacacs_creds, setup_limit):    # noqa F811
    """
        This test case will test following 2 scenarios:
            1. Following 2 templates can be render by hostcfgd correctly:
                    /usr/share/sonic/templates/pam_limits.j2
                    /usr/share/sonic/templates/limits.conf.j2
            2. SSH login session limit works correctly.
    """
    duthost = duthosts[rand_one_dut_hostname]

    # if template file not exist on duthost, ignore this UT
    pytest_require(limit_template_exist(
        duthost), "Template file {0} not exist, ignore test case.".format(LIMITS_CONF_TEMPLATE_PATH))

    dut_ip = duthost.mgmt_ip
    local_user = tacacs_creds['local_user']
    local_user_password = tacacs_creds['local_user_passwd']

    # Create multiple login session to test maxlogins limit, first session will success
    ssh_session_1 = paramiko_ssh(dut_ip, local_user, local_user_password)
    login_message_1 = get_login_result(ssh_session_1)

    logging.debug("Login session 1 result:\n{0}\n".format(login_message_1))
    pytest_assert("There were too many logins for" not in login_message_1,
                  "The first login was unexpectedly rejected due to too many logins")

    # The second session will be disconnect by device
    ssh_session_2 = paramiko_ssh(dut_ip, local_user, local_user_password)
    login_message_2 = get_login_result(ssh_session_2)

    logging.debug("Login session 2 result:\n{0}\n".format(login_message_2))
    pytest_assert("There were too many logins for" in login_message_2,
                  "The second login was not rejected by ssh limit")

    ssh_session_1.close()
    ssh_session_2.close()
