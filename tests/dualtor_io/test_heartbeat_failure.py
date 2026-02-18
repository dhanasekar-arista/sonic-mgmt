"""
=============================================================================
Module: dualtor_io
File: test_heartbeat_failure.py
=============================================================================

Description:
    Test suite for validating dual-ToR resilience during heartbeat (LinkProber) failures.
    This module tests failover behavior when the active or standby ToR loses heartbeat
    capability by stopping the LinkProber module in the mux container. Tests verify
    traffic disruption and proper mux state transitions during heartbeat loss scenarios.

Test Intent:
    - test_active_tor_heartbeat_failure_upstream: Verify traffic failover when active ToR heartbeat stops (server to T1)
    - test_active_tor_heartbeat_failure_downstream: Verify traffic failover when active ToR heartbeat stops (T1 to server)
    - test_standby_tor_heartbeat_failure_upstream: Verify standby ToR heartbeat stop does not affect traffic (server to T1)
    - test_standby_tor_heartbeat_failure_downstream: Verify standby ToR heartbeat stop does not affect traffic (T1 to server)

Topology:
    - dualtor: Dual-ToR topology with active-standby or active-active cable types

Fixtures Used:
    - upper_tor_host: Upper ToR DUT host object
    - lower_tor_host: Lower ToR DUT host object
    - toggle_all_simulator_ports_to_upper_tor: Sets all mux ports to upper ToR (active)
    - send_t1_to_server_with_action: Sends downstream traffic with action during transmission
    - send_server_to_t1_with_action: Sends upstream traffic with action during transmission
    - shutdown_tor_heartbeat: Stops LinkProber module in mux container to simulate heartbeat failure
    - run_icmp_responder: Runs ICMP responder on PTF for server simulation
    - run_garp_service: Runs GARP service on PTF for MAC address updates
    - change_mac_addresses: Changes PTF MAC addresses to match server MACs
    - check_simulator_flap_counter: Verifies mux simulator flap counts
    - cable_type: Cable type fixture (active-standby or active-active)

Dependencies:
    - Mux simulator control for cable state management
    - LinkProber process in mux container for heartbeat monitoring
    - PTF framework for traffic generation and verification
    - tor_failure_utils.shutdown_tor_heartbeat for stopping LinkProber
    - LogAnalyzer for expected error log validation

Notes:
    - Tests are marked with pytest.mark.topology("dualtor")
    - Disruption must be less than MUX_SIM_ALLOWED_DISRUPTION_SEC (1 second)
    - Expected log error: 'container_checker' status failed -- Expected containers not running: mux
    - Heartbeat failure is simulated by stopping LinkProber module (not entire mux container)
    - Active-standby: Heartbeat loss on active ToR triggers failover to standby
    - Active-standby: Heartbeat loss on standby ToR has no effect on traffic
    - Active-active: Both ToRs remain active even during heartbeat failures
    - LogAnalyzer ignores expected monit container checker errors during heartbeat loss
    - Tests verify control plane (mux state) and data plane (traffic forwarding)

=============================================================================
"""

import pytest

from tests.common.dualtor.control_plane_utils import verify_tor_states
from tests.common.dualtor.data_plane_utils import send_t1_to_server_with_action, \
                                                  send_server_to_t1_with_action                 # noqa: F401
from tests.common.dualtor.dual_tor_utils import upper_tor_host, lower_tor_host                  # noqa: F401
from tests.common.dualtor.dual_tor_utils import check_simulator_flap_counter                    # noqa: F401
from tests.common.dualtor.mux_simulator_control import toggle_all_simulator_ports_to_upper_tor  # noqa: F401
from tests.common.dualtor.tor_failure_utils import shutdown_tor_heartbeat                       # noqa: F401
from tests.common.fixtures.ptfhost_utils import run_icmp_responder, run_garp_service, \
                                                change_mac_addresses                            # noqa: F401
from tests.common.dualtor.constants import MUX_SIM_ALLOWED_DISRUPTION_SEC
from tests.common.dualtor.dual_tor_common import cable_type                                     # noqa: F401
from tests.common.dualtor.dual_tor_common import CableType


pytestmark = [
    pytest.mark.topology("dualtor")
]


@pytest.fixture(autouse=True)
def ignore_expected_loganalyzer_exception(loganalyzer, duthosts):

    ignore_errors = [
        r".* ERR monit.*: 'container_checker' status failed \(3\) -- Expected containers not running: mux"
    ]

    if loganalyzer:
        for duthost in duthosts:
            loganalyzer[duthost.hostname].ignore_regex.extend(ignore_errors)

    return None


def test_active_tor_heartbeat_failure_upstream(
    toggle_all_simulator_ports_to_upper_tor, upper_tor_host, lower_tor_host,    # noqa: F811
    send_server_to_t1_with_action, shutdown_tor_heartbeat, cable_type           # noqa: F811
):
    """
    Send upstream traffic and stop the LinkProber module on the active ToR.
    Confirm switchover and disruption lasts < 1 second.
    """
    send_server_to_t1_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        action=lambda: shutdown_tor_heartbeat(upper_tor_host)
    )

    if cable_type == CableType.active_standby:
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            cable_type=cable_type
        )

    if cable_type == CableType.active_active:
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            cable_type=cable_type
        )


@pytest.mark.enable_active_active
def test_active_tor_heartbeat_failure_downstream_active(
    toggle_all_simulator_ports_to_upper_tor, upper_tor_host, lower_tor_host,    # noqa: F811
    send_t1_to_server_with_action, shutdown_tor_heartbeat, cable_type           # noqa: F811
):
    """
    Send downstream traffic from T1 to the active ToR and stop the LinkProber module on the active ToR.
    Confirm switchover and disruption lasts < 1 second.
    """
    send_t1_to_server_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        action=lambda: shutdown_tor_heartbeat(upper_tor_host)
    )

    if cable_type == CableType.active_standby:
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            cable_type=cable_type
        )

    if cable_type == CableType.active_active:
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            cable_type=cable_type
        )


def test_active_tor_heartbeat_failure_downstream_standby(
        toggle_all_simulator_ports_to_upper_tor, upper_tor_host, lower_tor_host,    # noqa: F811
        send_t1_to_server_with_action, shutdown_tor_heartbeat):                     # noqa: F811
    """
    Send downstream traffic from T1 to the standby ToR and stop the LinkProber module on the active ToR.
    Confirm switchover and disruption lasts < 1 second.
    """
    send_t1_to_server_with_action(
        lower_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        action=lambda: shutdown_tor_heartbeat(upper_tor_host)
    )
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host
    )


def test_standby_tor_heartbeat_failure_upstream(
        toggle_all_simulator_ports_to_upper_tor, upper_tor_host, lower_tor_host,    # noqa: F811
        send_server_to_t1_with_action, shutdown_tor_heartbeat):                     # noqa: F811
    """
    Send upstream traffic and stop the LinkProber module on the standby ToR.
    Confirm no switchover and no disruption.
    """
    send_server_to_t1_with_action(
        upper_tor_host, verify=True,
        action=lambda: shutdown_tor_heartbeat(lower_tor_host)
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host
    )


def test_standby_tor_heartbeat_failure_downstream_active(
        toggle_all_simulator_ports_to_upper_tor, upper_tor_host, lower_tor_host,    # noqa: F811
        send_t1_to_server_with_action, shutdown_tor_heartbeat):                     # noqa: F811
    """
    Send downstream traffic from T1 to the active ToR and stop the LinkProber module on the standby ToR.
    Confirm no switchover and no disruption.
    """
    send_t1_to_server_with_action(
        upper_tor_host, verify=True,
        action=lambda: shutdown_tor_heartbeat(lower_tor_host)
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host
    )


def test_standby_tor_heartbeat_failure_downstream_standby(
        toggle_all_simulator_ports_to_upper_tor, upper_tor_host, lower_tor_host,    # noqa: F811
        send_t1_to_server_with_action, shutdown_tor_heartbeat):                     # noqa: F811
    """
    Send downstream traffic from T1 to the standby ToR and stop the LinkProber module on the standby ToR.
    Confirm no switchover and no disruption.
    """
    send_t1_to_server_with_action(
        lower_tor_host, verify=True,
        action=lambda: shutdown_tor_heartbeat(lower_tor_host)
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host
    )
