"""
=============================================================================
Module: dualtor_io
File: test_tor_bgp_failure.py
=============================================================================

Description:
    Test suite for validating dual-ToR resilience during BGP failures. This module tests
    failover behavior when BGP sessions or the BGP daemon fail on active or standby ToR.
    Tests verify traffic disruption and proper mux state transitions when BGP connectivity
    is lost, ensuring proper failover to maintain server reachability.

Test Intent:
    - test_bgp_shutdown_active_upstream: Verify traffic failover when active ToR BGP sessions are shut down (server to T1)
    - test_bgp_shutdown_standby_upstream: Verify standby ToR BGP shutdown does not affect traffic (server to T1)
    - test_kill_bgpd_active_upstream: Verify traffic failover when active ToR BGP daemon is killed (server to T1)
    - test_kill_bgpd_standby_upstream: Verify standby ToR BGP daemon kill does not affect traffic (server to T1)

Topology:
    - dualtor: Dual-ToR topology with active-standby or active-active cable types

Fixtures Used:
    - upper_tor_host: Upper ToR DUT host object
    - lower_tor_host: Lower ToR DUT host object
    - toggle_all_simulator_ports_to_upper_tor: Sets all mux ports to upper ToR (active)
    - send_t1_to_server_with_action: Sends downstream traffic with action during transmission
    - send_server_to_t1_with_action: Sends upstream traffic with action during transmission
    - shutdown_bgp_sessions: Shuts down BGP sessions on specified ToR
    - kill_bgpd: Kills BGP daemon (bgpd) on specified ToR
    - run_icmp_responder: Runs ICMP responder on PTF for server simulation
    - run_garp_service: Runs GARP service on PTF for MAC address updates
    - change_mac_addresses: Changes PTF MAC addresses to match server MACs
    - check_simulator_flap_counter: Verifies mux simulator flap counts
    - cable_type: Cable type fixture (active-standby or active-active)
    - tunnel_traffic_monitor: Monitors tunnel traffic during tests
    - temp_enable_bgp_autorestart: Module-level fixture to enable BGP autorestart

Dependencies:
    - Mux simulator control for cable state management
    - BGP container and bgpd daemon for routing
    - PTF framework for traffic generation and verification
    - tor_failure_utils for BGP shutdown and kill operations
    - config feature autorestart for BGP recovery

Notes:
    - Tests are marked with pytest.mark.topology("dualtor")
    - Disruption must be less than MUX_SIM_ALLOWED_DISRUPTION_SEC (1 second)
    - BGP autorestart is temporarily enabled for all tests (restored after module)
    - Out of scope cases: T1->Standby ToR->Server (Standby BGP Down), T1->Active ToR->Server (Active BGP Down)
    - Reason: Shutting down BGP means T1 won't send traffic to that ToR anyway
    - BGP session shutdown uses 'sudo config bgp shutdown neighbor <neighbor_ip>'
    - Kill bgpd uses 'docker exec bgp pkill -9 bgpd' to kill BGP daemon
    - BGP autorestart ensures bgpd automatically restarts after being killed
    - Active ToR BGP failure should trigger failover to standby ToR
    - Standby ToR BGP failure should not affect traffic (already on active)
    - Tests verify control plane (mux state) and data plane (traffic forwarding)

=============================================================================
"""

import pytest

from tests.common.dualtor.control_plane_utils import verify_tor_states
from tests.common.dualtor.data_plane_utils import send_t1_to_server_with_action, \
                                                  send_server_to_t1_with_action                     # noqa: F401
from tests.common.dualtor.dual_tor_utils import upper_tor_host, lower_tor_host                      # noqa: F401
from tests.common.dualtor.dual_tor_utils import check_simulator_flap_counter                        # noqa: F401
from tests.common.dualtor.mux_simulator_control import toggle_all_simulator_ports_to_upper_tor      # noqa: F401
from tests.common.dualtor.tor_failure_utils import kill_bgpd                                        # noqa: F401
from tests.common.dualtor.tor_failure_utils import shutdown_bgp_sessions                            # noqa: F401
from tests.common.dualtor.tor_failure_utils import shutdown_bgp_sessions_on_duthost
from tests.common.fixtures.ptfhost_utils import run_icmp_responder, run_garp_service, \
                                                change_mac_addresses                                # noqa: F401
from tests.common.dualtor.tunnel_traffic_utils import tunnel_traffic_monitor                        # noqa: F401
from tests.common.dualtor.constants import MUX_SIM_ALLOWED_DISRUPTION_SEC
from tests.common.dualtor.dual_tor_common import cable_type                                         # noqa: F401
from tests.common.dualtor.dual_tor_common import CableType


pytestmark = [
    pytest.mark.topology("dualtor")
]

'''
Below cases are out of scope:
Case: T1 -> Standby ToR -> Server (Standby ToR BGP Down)
Out of scope: taking down the standby ToR's BGP sessions means the T1 will never send traffic to that ToR
Case: T1 -> Active ToR -> Server (Active ToR BGP Down)
Out of scope: taking down the active ToR's BGP sessions means the T1 will never send traffic to that ToR

Remaining cases for bgp shutdown are defined in this module.
'''


@pytest.fixture(scope='module', autouse=True)
def temp_enable_bgp_autorestart(duthosts):
    autorestart_cmd = 'config feature autorestart bgp {}'
    config_save_cmd = 'config save -y'

    old_autorestart_vals = {}

    cmds = []
    cmds.append(autorestart_cmd.format('enabled'))
    cmds.append(config_save_cmd)

    for duthost in duthosts:
        autorestart_states = duthost.get_container_autorestart_states()
        old_autorestart_vals[duthost] = autorestart_states['bgp']
        duthost.shell_cmds(cmds=cmds)

    yield

    for duthost in duthosts:
        cmds = []
        old_state = old_autorestart_vals[duthost]
        cmds.append(autorestart_cmd.format(old_state))
        cmds.append(config_save_cmd)
        duthost.shell_cmds(cmds=cmds)


@pytest.fixture(autouse=True)
def ignore_expected_loganalyzer_exception(loganalyzer, duthosts):

    ignore_errors = [
        r".* ERR bgp#bgpmon: \*ERROR\* Failed with rc:1 when execute: vtysh -c 'show bgp summary json'",
        r".* ERR bgp#bgpmon: \*ERROR\* Failed with rc:1 when execute: \['vtysh', '-c', 'show bgp summary json'\]",
        r".* ERR syncd#syncd: .*SAI_API_TUNNEL:_brcm_sai_mptnl_tnl_route_event_add:\d+ ecmp table entry lookup "
        "failed with error.*",
        r".* ERR syncd#syncd: .*SAI_API_TUNNEL:_brcm_sai_mptnl_process_route_add_mode_default_and_host:\d+ "
        "_brcm_sai_mptnl_tnl_route_event_add failed with error.*",
        r".* ERR bgp#mgmtd\[\d+\]: \[X3G8F-PM93W\] BE-adapter: mgmt_msg_read: got EOF/disconnect",
        r".* ERR bgp#bgpmon: \*ERROR\* Failed with rc:1 when execute: "
        r"\['vtysh', '-H', '/dev/null', '-c', 'show bgp summary json'\]"
    ]

    if loganalyzer:
        for duthost in duthosts:
            loganalyzer[duthost.hostname].ignore_regex.extend(ignore_errors)

    return None


def test_active_tor_kill_bgpd_upstream(
        upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
        toggle_all_simulator_ports_to_upper_tor, kill_bgpd):                # noqa: F811
    '''
    Case: Server -> ToR -> T1 (Active ToR BGP Down)
    Action: Shutdown all BGP sessions on the active ToR
    Expectation:
        Verify packet flow after the active ToR (A) loses BGP sessions
        ToR A DBs indicate standby, ToR B DBs indicate active
        T1 switch receives packet from the initial standby ToR (B) and not the active ToR (A)
        Verify traffic interruption < threshold
    '''
    send_server_to_t1_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        action=lambda: kill_bgpd(upper_tor_host)
    )
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host
    )


def test_standby_tor_kill_bgpd_upstream(
        upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
        toggle_all_simulator_ports_to_upper_tor, kill_bgpd):                # noqa: F811
    '''
    Case: Server -> ToR -> T1 (Standby ToR BGP Down)
    Action: Shutdown all BGP sessions on the standby ToR
    Expectation:
        Verify packet flow after the standby ToR (B) loses BGP sessions
        ToR A DBs indicate active, ToR B DBs indicate standby
        T1 switch receives packet from the active ToR (A), and not the standby ToR (B)
    '''
    send_server_to_t1_with_action(
        upper_tor_host, verify=True,
        action=lambda: kill_bgpd(lower_tor_host)
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host
    )


def test_standby_tor_kill_bgpd_downstream_active(
        upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
        toggle_all_simulator_ports_to_upper_tor, kill_bgpd,                 # noqa: F811
        tunnel_traffic_monitor):                                            # noqa: F811
    '''
    Case: T1 -> Active ToR -> Server (Standby ToR BGP Down)
    Action: Shutdown all BGP sessions on the standby ToR
    Expectation:
        Verify packet flow after the standby ToR (B) loses BGP sessions
        T1 switch receives no IP-in-IP packet; server receives packet
    '''
    with tunnel_traffic_monitor(lower_tor_host, existing=False):
        send_t1_to_server_with_action(
            upper_tor_host, verify=True,
            action=lambda: kill_bgpd(lower_tor_host)
        )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host
    )


def test_active_tor_kill_bgpd_downstream_standby(
        upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
        toggle_all_simulator_ports_to_upper_tor, kill_bgpd,                 # noqa: F811
        tunnel_traffic_monitor):                                            # noqa: F811
    '''
    Case: T1 -> Standby ToR -> Server (Active ToR BGP Down)
    Action: Shutdown all BGP sessions on the active ToR
    Expectation:
        Verify packet flow after the active ToR (A) loses BGP sessions
        Verify ToR A standby, ToR B active
        Verify traffic interruption is < 1 second
    '''
    send_t1_to_server_with_action(
        lower_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        action=lambda: kill_bgpd(upper_tor_host)
    )
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host
    )


@pytest.mark.enable_active_active
def test_active_tor_shutdown_bgp_sessions_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_bgp_sessions, cable_type                                   # noqa: F811
):
    """
    Case: Server -> ToR -> T1 (Active ToR BGP Down)
    Action: Shutdown all BGP sessions on the active ToR
    Expectation:
        Verify packet flow after the active ToR (A) loses BGP sessions
        ToR A DBs indicate standby, ToR B DBs indicate active
        T1 switch receives packet from the initial standby ToR (B) and not the active ToR (A)
        Verify traffic interruption < threshold
    """
    if cable_type == CableType.active_standby:
        send_server_to_t1_with_action(
            upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            action=lambda: shutdown_bgp_sessions(upper_tor_host), random_dst=False
        )

    if cable_type == CableType.active_active:
        send_server_to_t1_with_action(
            upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            action=lambda: shutdown_bgp_sessions(upper_tor_host)
        )

    if cable_type == CableType.active_active:
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health="unhealthy",
            cable_type=cable_type
        )

    if cable_type == CableType.active_standby:
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health="unhealthy",
            cable_type=cable_type
        )


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_active_tor_shutdown_bgp_sessions_downstream(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    cable_type, tunnel_traffic_monitor                                  # noqa: F811
):
    """
    Case: T1 -> ToR -> Server (Upper ToR shutdown/startup BGP sessions)
    Action: Shutdown all BGP sessions on the upper ToR
    Expectation:
        Verify ToR changes to standby after shutdown all BGP sessions.
        Verify ToR comes back to active after startup all BGP sessions.
        Verify server receives packets after startup all BGP sessions, no tunnel traffic.
    """
    # verify all ToRs are in active state
    verify_tor_states(
        expected_active_host=[upper_tor_host, lower_tor_host],
        expected_standby_host=None,
        cable_type=cable_type
    )

    # verify the upper ToR changes to standby after shutdown BGP sessions
    with shutdown_bgp_sessions_on_duthost() as shutdown_bgp_sessions:   # noqa: F811
        shutdown_bgp_sessions(upper_tor_host)
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health="unhealthy",
            cable_type=cable_type
        )

    # verify the upper ToR changes back to active after startup BGP sessions
    verify_tor_states(
        expected_active_host=[upper_tor_host, lower_tor_host],
        expected_standby_host=None,
        cable_type=cable_type
    )

    # verify the server receives packets with no disrupts, no tunnel traffic
    with tunnel_traffic_monitor(upper_tor_host, existing=False):
        send_t1_to_server_with_action(upper_tor_host, verify=True, stop_after=60)
