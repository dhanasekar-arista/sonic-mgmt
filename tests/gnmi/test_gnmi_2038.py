"""
=============================================================================
Module: gnmi
File: test_gnmi_2038.py
=============================================================================

Description:
    Tests gNMI certificate handling for dates beyond the Year 2038 problem.
    Validates that certificates with expiration dates after 2038 work correctly
    with gNMI server.

Test Intent:
    - test_gnmi_capabilities_2038: Creates and validates certificates with
      expiration dates beyond 2038 (root: 4850 days, server/client: 4800 days)
      and verifies gNMI capabilities function correctly

Topology:
    Supports any topology

Fixtures Used:
    - duthosts: DUT host objects
    - rand_one_dut_hostname: Randomly selected DUT
    - localhost: Localhost for certificate preparation
    - ptfhost: PTF host for certificate copy

Dependencies:
    - tests.common.helpers.gnmi_utils: Certificate preparation and copy utilities
    - .helper: apply_cert_config
    - dateutil: parser for date parsing

Notes:
    - Log analyzer disabled for these tests
    - Root cert: 4850 days validity
    - Server/Client certs: 4800 days validity
    - Validates certificate dates are after 2038-01-19
    - Tests Year 2038 Unix timestamp overflow handling
=============================================================================
"""
import pytest
import logging
import re
from datetime import datetime, timezone
from dateutil import parser

from tests.common.helpers.gnmi_utils import gnmi_capabilities, prepare_root_cert, prepare_server_cert, \
    prepare_client_cert, copy_certificate_to_dut, copy_certificate_to_ptf
from .helper import apply_cert_config

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer,
    pytest.mark.usefixtures("setup_gnmi_ntp_client_server", "setup_gnmi_server",
                            "setup_gnmi_rotated_server", "check_dut_timestamp")
]

ROOT_CERT_DAYS = 4850
SERVER_CERT_DAYS = 4800
CLIENT_CERT_DAYS = 4800


def test_gnmi_capabilities_2038(duthosts, rand_one_dut_hostname, localhost, ptfhost):
    '''
    Verify certificate after 2038 year problem
    '''
    duthost = duthosts[rand_one_dut_hostname]

    prepare_root_cert(localhost, days=ROOT_CERT_DAYS)
    prepare_server_cert(duthost, localhost, days=SERVER_CERT_DAYS)
    prepare_client_cert(localhost, days=CLIENT_CERT_DAYS)

    copy_certificate_to_dut(duthost)
    copy_certificate_to_ptf(ptfhost)

    apply_cert_config(duthost)

    # Verify certificate date on DUT
    check_cert_date_on_dut(duthost)

    # Verify GNMI capabilities to validate functionality
    ret, msg = gnmi_capabilities(duthost, localhost)
    assert ret == 0, msg
    assert "sonic-db" in msg, msg
    assert "JSON_IETF" in msg, msg


def check_cert_date_on_dut(duthost):
    cmd = "openssl x509 -in /etc/sonic/telemetry/gnmiCA.pem -text"
    output = duthost.shell(cmd, module_ignore_errors=True)
    not_after_line = re.search(r"Not After\s*:\s*(.*)", output['stdout'])
    if not_after_line:
        not_after_date_str = not_after_line.group(1).strip()
        # Convert the date string to a datetime object
        expiry_date = parser.parse(not_after_date_str)
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
        # comparison date is January 20, 2038, after the 2038 problem
        after_2038_problem_date = datetime(2038, 1, 20, tzinfo=timezone.utc)

        if expiry_date < after_2038_problem_date:
            raise Exception("The expiry date {} is not after 2038 problem date".format(expiry_date))
        else:
            logger.info("The expiry date {} is after January 20, 2038.".format(expiry_date))
    else:
        raise Exception("The 'Not After' line with expiry date was not found")
