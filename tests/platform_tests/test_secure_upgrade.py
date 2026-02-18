"""
=============================================================================
Module: platform_tests
File: test_secure_upgrade.py
=============================================================================

Description:
    Tests secure upgrade feature. Validates that secure systems reject non-secure
    image installations and display appropriate error messages. Ensures security
    policies are enforced during image upgrade.

Test Intent:
    - test_secure_upgrade: Verify secure system rejects non-secure image installation
      with appropriate error message

Topology:
    Any topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - localhost: Localhost connection
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hardware SKU
    - keep_same_version_installed: Function-scoped fixture restoring original image

Dependencies:
    - install_sonic helper for image installation
    - --target_image_list CLI option (must contain non-secure image path)

Notes:
    - Test requires --target_image_list with non-secure image path
    - Example: pytest platform_tests/test_secure_upgrade.py --target_image_list non_secure.bin
    - Validates installation fails for non-secure image on secure system
    - Checks for security rejection message in output
    - keep_same_version_installed fixture restores original image post-test
    - Uses RunAnsibleModuleFail to catch expected installation failure
    - Loganalyzer disabled (expected error logs during failed install)
    - Test validates security enforcement in upgrade path
=============================================================================
"""
import logging
import pytest
import re
from tests.common.errors import RunAnsibleModuleFail
from tests.common.helpers.assertions import pytest_assert
from tests.common.helpers.upgrade_helpers import install_sonic

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer,
]

logger = logging.getLogger(__name__)


@pytest.fixture(scope='function', autouse=True)
def keep_same_version_installed(duthost):
    '''
    @summary: extract the current version installed as shown in the "show boot" output
    and restore original image installed after the test run
    :param duthost: device under test
    '''
    output = duthost.shell("show boot")['stdout']
    results = re.findall(r"Current\s*\:\s*(.*)\n", output)
    pytest_assert(len(results) > 0, "Current image is empty!")
    current_version = results[0]
    yield
    duthost.shell("sudo sonic-installer set-default {}".format(current_version))


@pytest.fixture(scope='session')
def non_secure_image_path(request):
    '''
    @summary: will extract the non secure image path from --target_image_list parameter
    :return: given non secure image path
    '''
    non_secure_img_path = request.config.getoption('target_image_list')

    if not non_secure_img_path:
        pytest.skip("Skip test case since parameter '--target_image_list' is not specified")

    return str(non_secure_img_path)


def test_non_secure_boot_upgrade_failure(duthost, non_secure_image_path, tbinfo):
    """
    @summary: This test case validates non successful upgrade of a given non secure image
    """
    secure_boot_image = duthost.command("sonic-cfggen  -y /etc/sonic/sonic_version.yml -v secure_boot_image")['stdout']

    if secure_boot_image != 'yes':
        pytest.skip("Current Image is not secured so skipping")

    # install non secure image
    logger.info("install non secure image - expect fail, image path = {}".format(non_secure_image_path))
    result = "image install failure"  # because we expect fail
    try:
        # in case of success result will take the target image name
        result = install_sonic(duthost, non_secure_image_path, tbinfo)
    except RunAnsibleModuleFail as err:
        err_msg = str(err.results._check_key("msg"))
        logger.info("Expected fail, err msg is : {}".format(err_msg))
        pytest_assert(
            "Failure: CMS signature Verification Failed" in str(err_msg),
            "failure was not due to security limitations")
    finally:
        pytest_assert(result == "image install failure", "non-secure image was successfully installed")
