"""
=============================================================================
Module: system_health
File: test_system_status.py
=============================================================================

Description:
    This test file validates that the SONiC system reaches a fully running state
    after boot or reload. It checks the systemd system status to ensure all
    required services have started and the system is no longer in "starting" state.

Test Intent:
    - test_system_is_running: Validates that the system completes its boot/initialization
      sequence by polling 'systemctl is-system-running' every 10 seconds for up to
      180 seconds, waiting until the status changes from "starting" to a stable
      state (running, degraded, etc.), ensuring all critical services are initialized.

Topology:
    any (works with any topology type)

Fixtures Used:
    - duthost: DUT host object for executing commands and checking system status

Dependencies:
    - pytest: Test framework
    - tests.common.utilities: Provides wait_until helper for polling operations

Notes:
    - Maximum wait time: 180 seconds (3 minutes)
    - Poll interval: 10 seconds
    - Checks systemd overall system state via 'systemctl is-system-running'
    - Possible systemd states: initializing, starting, running, degraded, maintenance, stopping
    - Test passes when state is no longer "starting"
    - Test fails if system remains in "starting" state for full 180 seconds
    - Useful for validating system readiness after boot, reload, or upgrade
=============================================================================
"""
import pytest

from tests.common.utilities import wait_until

pytestmark = [
    pytest.mark.topology('any')
]


def test_system_is_running(duthost):
    def is_system_ready(duthost):
        status = duthost.shell('sudo systemctl is-system-running', module_ignore_errors=True)['stdout']
        return status != "starting"

    if not wait_until(180, 10, 0, is_system_ready, duthost):
        pytest.fail('Failed to find routed interface in 180 s')
