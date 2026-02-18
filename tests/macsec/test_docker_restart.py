"""
=============================================================================
Module: macsec
File: test_docker_restart.py
=============================================================================

Description:
    This test validates MACsec resilience when the MACsec Docker container is
    restarted. It ensures MACsec sessions are re-established and APPL_DB
    entries are restored after service restart.

Test Intent:
    - test_restart_macsec_docker: Validates that MACsec functionality is fully
      restored after restarting the MACsec Docker container. Restarts the
      macsec service with start-limit guard protection (35s backoff, 180s
      verify timeout), then verifies APPL_DB entries are correctly populated
      with expected policy, cipher suite, and send_sci settings within 300
      seconds. Ensures MACsec service restart does not cause permanent session
      loss.

Topology:
    t2 topology with MACsec support required

Fixtures Used:
    - duthosts: Provides list of DUT hosts for testing
    - ctrl_links: Dictionary of MACsec-controlled links on the DUT
    - policy: MACsec policy configuration
    - cipher_suite: MACsec cipher suite (e.g., GCM-AES-128, GCM-AES-256)
    - send_sci: Whether to send SCI in MACsec frames
    - enum_rand_one_per_hwsku_macsec_frontend_hostname: Selects one random
      MACsec-capable frontend DUT per hardware SKU

Dependencies:
    - tests.common.utilities: For wait_until polling functionality
    - tests.common.macsec.macsec_helper: For APPL_DB validation
    - tests.common.helpers.dut_utils: For service restart with start-limit guard

Notes:
    - Only runs on t2 topology
    - Uses start-limit guard to prevent systemd rate limiting issues
    - Backoff period: 35 seconds
    - Verify timeout: 180 seconds
    - Waits up to 300 seconds for APPL_DB restoration after restart
    - Logs Docker container status before and after restart for debugging
=============================================================================
"""
import pytest
import logging

from tests.common.utilities import wait_until
from tests.common.macsec.macsec_helper import check_appl_db
from tests.common.helpers.dut_utils import restart_service_with_startlimit_guard


logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.macsec_required,
    pytest.mark.topology('t2')
]


def test_restart_macsec_docker(duthosts, ctrl_links, policy, cipher_suite, send_sci,
                               enum_rand_one_per_hwsku_macsec_frontend_hostname):
    duthost = duthosts[enum_rand_one_per_hwsku_macsec_frontend_hostname]

    logger.info(duthost.shell(cmd="docker ps", module_ignore_errors=True)['stdout'])
    restart_service_with_startlimit_guard(duthost, "macsec", backoff_seconds=35, verify_timeout=180)
    logger.info(duthost.shell(cmd="docker ps", module_ignore_errors=True)['stdout'])
    assert wait_until(300, 6, 12, check_appl_db, duthost, ctrl_links, policy, cipher_suite, send_sci)
