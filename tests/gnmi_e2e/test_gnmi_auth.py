"""
=============================================================================
Module: gnmi_e2e
File: test_gnmi_auth.py
=============================================================================

Description:
    End-to-end tests for gNMI authentication and authorization. Validates
    certificate common name (CN) based authentication and error handling for
    invalid certificates.

Test Intent:
    - test_gnmi_authorize_passed_with_valid_cname: Validates gNMI capabilities
      work with valid client certificate CN and no authentication errors occur
    - test_gnmi_authorize_failed_with_invalid_cname: Verifies gNMI rejects
      requests with invalid client certificate CN and returns "Unauthenticated"

Topology:
    Supports any topology

Fixtures Used:
    - duthosts: DUT host objects
    - rand_one_dut_hostname: Randomly selected DUT
    - localhost: Localhost for gNMI client
    - setup_invalid_client_cert_cname: Sets up invalid client cert for testing

Dependencies:
    - tests.common.helpers.gnmi_utils: gnmi_capabilities
    - tests.common.plugins.allure_wrapper: allure for test reporting
    - tests.gnmi_e2e.helper: setup_invalid_client_cert_cname

Notes:
    - Log analyzer disabled for these tests
    - Tests certificate-based authentication
    - Validates "Unauthenticated" error for invalid CN
=============================================================================
"""
import pytest
import logging

from tests.common.helpers.gnmi_utils import gnmi_capabilities
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.gnmi_e2e.helper import setup_invalid_client_cert_cname        # noqa: F401

logger = logging.getLogger(__name__)
allure.logger = logger

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer
]


def test_gnmi_authorize_passed_with_valid_cname(duthosts,
                                                rand_one_dut_hostname,
                                                localhost):
    '''
    Verify GNMI native write, incremental config for configDB
    GNMI set request with invalid path
    '''
    duthost = duthosts[rand_one_dut_hostname]
    ret, msg = gnmi_capabilities(duthost, localhost)
    logger.debug("test_gnmi_authorize_passed_with_valid_cname: {}".format(msg))

    assert "Unauthenticated" not in msg, (
        "'Unauthenticated' error message found in GNMI response. "
        "- Actual message: '{}'"
    ).format(msg)


def test_gnmi_authorize_failed_with_invalid_cname(duthosts,
                                                  rand_one_dut_hostname,
                                                  localhost,
                                                  setup_invalid_client_cert_cname):    # noqa: F811
    '''
    Verify GNMI native write, incremental config for configDB
    GNMI set request with invalid path
    '''
    duthost = duthosts[rand_one_dut_hostname]
    ret, msg = gnmi_capabilities(duthost, localhost)
    logger.debug("test_gnmi_authorize_failed_with_invalid_cname: {}".format(msg))

    assert "Unauthenticated" in msg, (
        "'Unauthenticated' error message not found in GNMI response. "
        "- Actual message: '{}'"
    ).format(msg)
