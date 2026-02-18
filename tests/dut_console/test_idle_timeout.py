"""
=============================================================================
Module: dut_console
File: test_idle_timeout.py
=============================================================================

Description:
    Test suite for validating console session idle timeout functionality on SONiC devices.
    This module tests that the TMOUT environment variable correctly controls automatic
    logout behavior after a period of inactivity on console sessions.

Test Intent:
    - test_timeout: Verify console session logs out automatically after configured idle timeout period

Topology:
    - any: Test works on any topology (t0, t1, t2, m0, mx, etc.)

Fixtures Used:
    - duthost_console: Console connection to DUT
    - duthosts: All DUT hosts in the testbed
    - enum_supervisor_dut_hostname: Supervisor DUT hostname (for chassis)

Dependencies:
    - Console connection via picocom or SSH
    - TMOUT environment variable for idle timeout control
    - Login prompt detection for timeout verification

Notes:
    - Test is marked with pytest.mark.topology('any')
    - Default idle timeout: 900 seconds (15 minutes)
    - Test sets timeout to 10 seconds for faster validation
    - Test waits 15 seconds (> 10 second timeout) to trigger logout
    - Expected behavior: Console returns to login prompt after idle timeout
    - TMOUT is a bash shell variable that logs out inactive sessions
    - Test verifies both getting and setting TMOUT value
    - Login prompt pattern: "<hostname> login:"

=============================================================================
"""

import logging
import time

import pytest

from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

DEFAULT_TMOUT = "900"
SET_TMOUT = "10"

pytestmark = [
    pytest.mark.topology('any')
]


def test_timeout(duthost_console, duthosts, enum_rand_one_per_hwsku_hostname):
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    logger.info("Get default session idle timeout")
    default_tmout = duthost_console.send_command('echo $TMOUT').strip().splitlines()[0].strip()
    pytest_assert(default_tmout == DEFAULT_TMOUT, "default timeout on dut is not {} seconds".format(DEFAULT_TMOUT))

    logger.info("Set session idle timeout")
    duthost_console.send_command('export TMOUT={}'.format(SET_TMOUT))
    set_tmout = duthost_console.send_command('echo $TMOUT').strip().splitlines()[0].strip()
    pytest_assert(set_tmout == SET_TMOUT, "set timeout fail")

    time.sleep(15)
    duthost_console.send_command("\n", expect_string=r"{} login:".format(duthost.hostname))
