"""
=============================================================================
Module: ssh
File: test_ssh_default_password.py
=============================================================================

Description:
    This test file verifies that the default SSH credentials for SONiC devices are
    correctly configured according to the image type. It ensures that SSH access
    using expected default username and password works as intended, which is
    important for initial device setup and automation workflows that rely on
    default credentials before password customization.

Test Intent:
    - test_ssh_default_password: Validates that SSH connection to the DUT succeeds
      using the expected default username and password based on the SONiC image type
      (e.g., different credentials for ONIE vs regular SONiC images). The test
      retrieves image-specific default credentials and attempts SSH authentication,
      failing if the expected credentials don't work.

Topology:
    any (works with any topology type)

Fixtures Used:
    - duthost: AnsibleHost instance providing access to the DUT for SSH connection
      testing and image type detection

Dependencies:
    - pytest: Test framework
    - paramiko: For SSH client functionality
    - tests.common.constants: Provides DEFAULT_SSH_CONNECT_PARAMS mapping
    - tests.common.utilities: Provides get_image_type function

Notes:
    - Test is marked to disable log analyzer
    - Default credentials vary based on SONiC image type
    - Uses paramiko with allow_agent=False and look_for_keys=False to ensure
      only password authentication is tested
    - Raises AuthenticationException if default password doesn't work
    - Important for validating initial device access in automation scenarios
=============================================================================
"""
import pytest
import paramiko
import logging
from tests.common.constants import DEFAULT_SSH_CONNECT_PARAMS
from tests.common.utilities import get_image_type

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology("any")
]

logger = logging.getLogger(__name__)


def test_ssh_default_password(duthost):
    """verify the initial SSH password is always expected.

    Args:
        duthost: AnsibleHost instance for DUT
    """
    # Check SONiC image type and get default username and password to SSH connect
    default_username_password = DEFAULT_SSH_CONNECT_PARAMS[get_image_type(
        duthost=duthost)]

    logger.info("current login params:\tusername={}, password={}".format(default_username_password["username"],
                                                                         default_username_password["password"]))

    # Test SSH connect with expected username and password
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(duthost.mgmt_ip, username=default_username_password["username"],
                    password=default_username_password["password"], allow_agent=False,
                    look_for_keys=False)
    except paramiko.AuthenticationException:
        logger.info(
            "SSH connect failed. Make sure use the expected password according to the SONiC image.")
        raise
