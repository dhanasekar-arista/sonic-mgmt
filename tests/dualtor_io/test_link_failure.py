"""
=============================================================================
Module: dualtor_io
File: test_link_failure.py
=============================================================================

Description:
    Test suite for validating dual-ToR resilience and traffic forwarding during link failures.
    This module tests failover behavior when uplinks (ToR to T1) or downlinks (ToR to server)
    are shut down on active or standby ToR. Tests cover both fanout-level interface shutdown
    and ToR-level interface shutdown scenarios with traffic verification.

Test Intent:
    - test_active_link_down_upstream: Verify traffic failover when active ToR uplink is shut down (server to T1)
    - test_standby_link_down_upstream: Verify standby ToR uplink shutdown does not affect traffic
    - test_active_link_down_downstream_active: Verify traffic failover when active ToR downlink is shut down (T1 to server)
    - test_active_link_down_downstream_standby: Verify standby ToR downlink shutdown does not affect traffic (T1 to server)
    - test_active_link_down_downstream_active_soc_inband: Verify SoC inband traffic failover when active ToR downlink is shut down
    - test_standby_link_down_downstream_active_soc_inband: Verify standby ToR downlink shutdown does not affect SoC inband traffic
    - test_tor_switch_downstream_active: Verify ToR switch interface shutdown causes failover (downstream active server)
    - test_tor_switch_downstream_standby: Verify ToR switch interface shutdown on standby does not affect traffic

Topology:
    - dualtor: Dual-ToR topology with active-standby or active-active cable types

Fixtures Used:
    - upper_tor_host: Upper ToR DUT host object
    - lower_tor_host: Lower ToR DUT host object
    - toggle_all_simulator_ports_to_upper_tor: Sets all mux ports to upper ToR (active)
    - send_t1_to_server_with_action: Sends downstream traffic with action during transmission
    - send_server_to_t1_with_action: Sends upstream traffic with action during transmission
    - send_soc_to_t1_with_action: Sends SoC to T1 traffic with action
    - send_t1_to_soc_with_action: Sends T1 to SoC traffic with action
    - shutdown_fanout_upper_tor_intfs: Shuts down fanout interfaces connected to upper ToR
    - shutdown_fanout_lower_tor_intfs: Shuts down fanout interfaces connected to lower ToR
    - shutdown_upper_tor_downlink_intfs: Shuts down upper ToR downlink interfaces
    - shutdown_lower_tor_downlink_intfs: Shuts down lower ToR downlink interfaces
    - run_icmp_responder: Runs ICMP responder on PTF for server simulation
    - run_garp_service: Runs GARP service on PTF for MAC address updates
    - change_mac_addresses: Changes PTF MAC addresses to match server MACs
    - check_simulator_flap_counter: Verifies mux simulator flap counts
    - cable_type: Cable type fixture (active-standby or active-active)
    - mux_config: Mux configuration fixture
    - active_active_ports: Active-active port configuration

Dependencies:
    - Mux simulator control for cable state management
    - Fanout switch access for upstream interface shutdown
    - PTF framework for traffic generation and verification
    - config_reload utility for ToR configuration recovery

Notes:
    - Tests are marked with pytest.mark.topology("dualtor")
    - Disruption must be less than MUX_SIM_ALLOWED_DISRUPTION_SEC (1 second)
    - Active-active tests are marked with @pytest.mark.enable_active_active
    - Fanout tests shut down interfaces at fanout level (upstream links)
    - ToR switch tests shut down interfaces at ToR level (downlink links)
    - Some platforms (Cisco, Mellanox) allow packet duplication during failover
    - Duplication settings: allowed_duplication and merge_duplications_into_disruptions
    - Tests verify control plane (mux state) and data plane (traffic forwarding)
    - Active-active cable tests verify all ports remain active during standby failures

=============================================================================
"""

import pytest

from tests.common.dualtor.control_plane_utils import verify_tor_states
from tests.common.dualtor.data_plane_utils import send_t1_to_server_with_action, send_server_to_t1_with_action, \
                                                  send_soc_to_t1_with_action, send_t1_to_soc_with_action    # noqa: F401
from tests.common.dualtor.dual_tor_utils import upper_tor_host, lower_tor_host, shutdown_fanout_upper_tor_intfs, \
                                                shutdown_fanout_lower_tor_intfs, upper_tor_fanouthosts, \
                                                lower_tor_fanouthosts, shutdown_upper_tor_downlink_intfs, \
                                                shutdown_lower_tor_downlink_intfs                   # noqa: F401
from tests.common.dualtor.dual_tor_utils import check_simulator_flap_counter                        # noqa: F401
from tests.common.dualtor.mux_simulator_control import toggle_all_simulator_ports_to_upper_tor      # noqa: F401
from tests.common.fixtures.ptfhost_utils import run_icmp_responder, run_garp_service, \
                                                change_mac_addresses       # noqa: F401
from tests.common.dualtor.constants import MUX_SIM_ALLOWED_DISRUPTION_SEC
from tests.common.dualtor.dual_tor_common import active_active_ports                                # noqa: F401
from tests.common.dualtor.dual_tor_common import mux_config                                         # noqa: F401
from tests.common.dualtor.dual_tor_common import cable_type                                         # noqa: F401
from tests.common.dualtor.dual_tor_common import CableType
from tests.common.config_reload import config_reload


pytestmark = [
    pytest.mark.topology("dualtor")
]


@pytest.fixture
def link_down_downstream_active_duplication_setting(duthost, mux_config):   # noqa: F811
    """Setup duplication setting based on the platform."""
    hwsku = duthost.facts['hwsku'].lower()
    allowed_duplication = None
    merge_duplications_into_disruptions = False
    if "cisco" in hwsku or "mellanox" in hwsku:
        allowed_duplication = (1, len(mux_config))
        merge_duplications_into_disruptions = True
    return allowed_duplication, merge_duplications_into_disruptions


@pytest.mark.enable_active_active
def test_active_link_down_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_fanout_upper_tor_intfs, cable_type                         # noqa: F811
):
    """
    Send traffic from server to T1 and shutdown the active ToR link.
    Verify switchover and disruption lasts < 1 second
    """
    if cable_type == CableType.active_active:
        send_server_to_t1_with_action(
            upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=1, action=shutdown_fanout_upper_tor_intfs
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health='unhealthy',
            cable_type=cable_type,
            skip_state_db=True
        )

    if cable_type == CableType.active_standby:
        send_server_to_t1_with_action(
            upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=3, action=shutdown_fanout_upper_tor_intfs
        )

        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health='unhealthy',
            cable_type=cable_type,
        )


@pytest.mark.enable_active_active
def test_active_link_down_downstream_active(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_fanout_upper_tor_intfs, cable_type,                        # noqa: F811
    link_down_downstream_active_duplication_setting                     # noqa: F811
):
    """
    Send traffic from T1 to active ToR and shutdown the active ToR link.
    Verify switchover and disruption lasts < 1 second
    """
    if cable_type == CableType.active_standby:
        send_t1_to_server_with_action(
            upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=3, action=shutdown_fanout_upper_tor_intfs
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health='unhealthy'
        )

    if cable_type == CableType.active_active:
        allowed_duplication, merge_duplications = link_down_downstream_active_duplication_setting
        send_t1_to_server_with_action(
            upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=1, allowed_duplication=allowed_duplication,
            action=shutdown_fanout_upper_tor_intfs,
            merge_duplications_into_disruptions=merge_duplications
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health='unhealthy',
            cable_type=cable_type,
            skip_state_db=True
        )


def test_active_link_down_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_fanout_upper_tor_intfs                                     # noqa: F811
):
    """
    Send traffic from T1 to standby ToR and shutdown the active ToR link.
    Verify switchover and disruption lasts < 1 second
    """
    send_t1_to_server_with_action(
        lower_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=3, action=shutdown_fanout_upper_tor_intfs
    )
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host,
        expected_standby_health='unhealthy'
    )


def test_standby_link_down_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_fanout_lower_tor_intfs                                     # noqa: F811
):
    """
    Send traffic from server to T1 and shutdown the standby ToR link.
    Verify no switchover and no disruption
    """
    send_server_to_t1_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=2, action=shutdown_fanout_lower_tor_intfs
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health='unhealthy'
    )


def test_standby_link_down_downstream_active(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_fanout_lower_tor_intfs                                     # noqa: F811
):
    """
    Send traffic from T1 to active ToR and shutdown the standby ToR link.
    Confirm no switchover and no disruption
    """
    send_t1_to_server_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=2, action=shutdown_fanout_lower_tor_intfs
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health='unhealthy'
    )


def test_standby_link_down_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_fanout_lower_tor_intfs                                     # noqa: F811
):
    """
    Send traffic from T1 to standby ToR and shutdwon the standby ToR link.
    Confirm no switchover and no disruption
    """
    send_t1_to_server_with_action(
        lower_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=2, action=shutdown_fanout_lower_tor_intfs
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health='unhealthy'
    )


def test_active_tor_downlink_down_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_upper_tor_downlink_intfs                                   # noqa: F811
):
    """
    Send traffic from server to T1 and shutdown the active ToR downlink on DUT.
    Verify switchover and disruption lasts < 1 second
    """
    send_server_to_t1_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=1, action=shutdown_upper_tor_downlink_intfs
    )
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host,
        expected_standby_health='unhealthy'
    )


def test_active_tor_downlink_down_downstream_active(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_upper_tor_downlink_intfs                                   # noqa: F811
):
    """
    Send traffic from T1 to active ToR and shutdown the active ToR downlink on DUT.
    Verify switchover and disruption lasts < 1 second
    """
    send_t1_to_server_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=1, action=shutdown_upper_tor_downlink_intfs
    )
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host,
        expected_standby_health='unhealthy'
    )


def test_active_tor_downlink_down_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_upper_tor_downlink_intfs                                   # noqa: F811
):
    """
    Send traffic from T1 to standby ToR and shutdown the active ToR downlink on DUT.
    Verify switchover and disruption lasts < 1 second
    """
    send_t1_to_server_with_action(
        lower_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=1, action=shutdown_upper_tor_downlink_intfs
    )
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host,
        expected_standby_health='unhealthy'
    )


def test_standby_tor_downlink_down_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_lower_tor_downlink_intfs                                   # noqa: F811
):
    """
    Send traffic from server to T1 and shutdown the standby ToR downlink on DUT.
    Verify no switchover and no disruption
    """
    send_server_to_t1_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=1, action=shutdown_lower_tor_downlink_intfs
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health='unhealthy'
    )


def test_standby_tor_downlink_down_downstream_active(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_lower_tor_downlink_intfs                                   # noqa: F811
):
    """
    Send traffic from T1 to active ToR and shutdown the standby ToR downlink on DUT.
    Confirm no switchover and no disruption
    """
    send_t1_to_server_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=1, action=shutdown_lower_tor_downlink_intfs
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health='unhealthy'
    )


def test_standby_tor_downlink_down_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor,                            # noqa: F811
    shutdown_lower_tor_downlink_intfs                                   # noqa: F811
):
    """
    Send traffic from T1 to standby ToR and shutdwon the standby ToR downlink on DUT.
    Confirm no switchover and no disruption
    """
    send_t1_to_server_with_action(
        lower_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=1, action=shutdown_lower_tor_downlink_intfs
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health='unhealthy'
    )


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_active_link_down_upstream_soc(
    upper_tor_host, lower_tor_host, send_soc_to_t1_with_action,         # noqa: F811
    shutdown_fanout_upper_tor_intfs, cable_type                         # noqa: F811
):
    """
    Send traffic from soc to T1 and shutdown the active ToR link.
    Verify switchover and disruption lasts < 1 second
    """
    if cable_type == CableType.active_active:
        send_soc_to_t1_with_action(
            upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=1, action=shutdown_fanout_upper_tor_intfs
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health='unhealthy',
            cable_type=cable_type,
            skip_state_db=True
        )


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_active_link_down_downstream_active_soc(
    upper_tor_host, lower_tor_host, send_t1_to_soc_with_action,         # noqa: F811
    shutdown_fanout_upper_tor_intfs, cable_type,                        # noqa: F811
    link_down_downstream_active_duplication_setting                     # noqa: F811
):
    """
    Send traffic from T1 to active ToR and shutdown the active ToR link.
    Verify switchover and disruption lasts < 1 second
    """
    if cable_type == CableType.active_active:
        allowed_duplication, merge_duplications = link_down_downstream_active_duplication_setting
        send_t1_to_soc_with_action(
            upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=1, allowed_duplication=allowed_duplication,
            action=shutdown_fanout_upper_tor_intfs,
            merge_duplications_into_disruptions=merge_duplications
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health='unhealthy',
            cable_type=cable_type,
            skip_state_db=True
        )


def config_interface_admin_status(duthost, ports, admin_status="up"):
    """Config interface admin status."""
    if admin_status == "up":
        cmd = "config interface startup %s"
    elif admin_status == "down":
        cmd = "config interface shutdown %s"
    else:
        return

    cmds = []
    for port in ports:
        cmds.append(cmd % port)
    duthost.shell_cmds(cmds=cmds)


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_active_link_admin_down_config_reload_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,       # noqa: F811
    cable_type, active_active_ports                                      # noqa: F811
):
    if cable_type == CableType.active_active:
        try:
            config_interface_admin_status(upper_tor_host, active_active_ports, "down")

            upper_tor_host.shell("config save -y")

            send_server_to_t1_with_action(
                lower_tor_host, verify=True, allowed_disruption=0,
                action=lambda: config_reload(upper_tor_host, wait=0)
            )

            verify_tor_states(
                expected_active_host=lower_tor_host,
                expected_standby_host=upper_tor_host,
                expected_standby_health='unhealthy',
                cable_type=cable_type,
                skip_state_db=True,  # state db will be 'unknown'
                verify_db_timeout=60
            )

        finally:
            config_interface_admin_status(upper_tor_host, active_active_ports, "up")
            upper_tor_host.shell("config save -y")


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_active_link_admin_down_config_reload_downstream(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,       # noqa: F811
    cable_type, active_active_ports                                      # noqa: F811
):
    if cable_type == CableType.active_active:
        try:
            config_interface_admin_status(upper_tor_host, active_active_ports, "down")

            upper_tor_host.shell("config save -y")
            config_reload(upper_tor_host, safe_reload=True, wait_for_bgp=True)

            verify_tor_states(
                expected_active_host=lower_tor_host,
                expected_standby_host=upper_tor_host,
                expected_standby_health='unhealthy',
                cable_type=cable_type,
                skip_state_db=True
            )

            send_t1_to_server_with_action(
                upper_tor_host, verify=True,
                stop_after=60,
                allowed_disruption=0,
                allow_disruption_before_traffic=True
            )

        finally:
            config_interface_admin_status(upper_tor_host, active_active_ports, "up")
            upper_tor_host.shell("config save -y")


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_active_link_admin_down_config_reload_link_up_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    cable_type, active_active_ports, setup_loganalyzer                  # noqa: F811
):
    """
    Send traffic from server to T1 and unshut the active-active mux ports.
    Verify switchover and disruption.
    """
    setup_loganalyzer(upper_tor_host, collect_only=True)
    if cable_type == CableType.active_active:
        try:
            config_interface_admin_status(upper_tor_host, active_active_ports, "down")

            verify_tor_states(
                expected_active_host=lower_tor_host,
                expected_standby_host=upper_tor_host,
                expected_standby_health='unhealthy',
                cable_type=cable_type,
                skip_state_db=True
            )

            upper_tor_host.shell("config save -y")
            config_reload(upper_tor_host, safe_reload=True, wait_for_bgp=True)

            verify_tor_states(
                expected_active_host=lower_tor_host,
                expected_standby_host=upper_tor_host,
                expected_standby_health='unhealthy',
                cable_type=cable_type,
                skip_state_db=True,
                verify_db_timeout=60
            )

            send_server_to_t1_with_action(
                upper_tor_host,
                verify=True,
                allowed_disruption=0,
                action=lambda: config_interface_admin_status(upper_tor_host, active_active_ports, "up")
            )

            verify_tor_states(
                expected_active_host=[upper_tor_host, lower_tor_host],
                expected_standby_host=None,
                cable_type=cable_type
            )

        finally:
            config_interface_admin_status(upper_tor_host, active_active_ports, "up")
            upper_tor_host.shell("config save -y")


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_active_link_admin_down_config_reload_link_up_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa F811
    cable_type, active_active_ports, setup_loganalyzer,                 # noqa F811
    link_down_downstream_active_duplication_setting                     # noqa F811
):
    """
    Send traffic from T1 to standby ToR and unshut the active-active mux ports.
    Verify switchover and disruption.
    """
    setup_loganalyzer(upper_tor_host, collect_only=True)
    if cable_type == CableType.active_active:
        try:
            config_interface_admin_status(upper_tor_host, active_active_ports, "down")

            verify_tor_states(
                expected_active_host=lower_tor_host,
                expected_standby_host=upper_tor_host,
                expected_standby_health='unhealthy',
                cable_type=cable_type,
                skip_state_db=True
            )

            upper_tor_host.shell("config save -y")
            config_reload(upper_tor_host, safe_reload=True, wait_for_bgp=True)

            verify_tor_states(
                expected_active_host=lower_tor_host,
                expected_standby_host=upper_tor_host,
                expected_standby_health='unhealthy',
                cable_type=cable_type,
                skip_state_db=True,
                verify_db_timeout=60
            )

            # after config reload, it takes time to setup the zero-mac tunnel routes for
            # the mux server ips, so there will be disruption before traffic.
            allowed_duplication, merge_duplications = \
                link_down_downstream_active_duplication_setting
            send_t1_to_server_with_action(
                upper_tor_host,
                verify=True,
                allowed_disruption=0,
                action=lambda: config_interface_admin_status(upper_tor_host, active_active_ports, "up"),
                allow_disruption_before_traffic=True,
                allowed_duplication=allowed_duplication,
                merge_duplications_into_disruptions=merge_duplications,
                delay=MUX_SIM_ALLOWED_DISRUPTION_SEC
            )

            verify_tor_states(
                expected_active_host=[upper_tor_host, lower_tor_host],
                expected_standby_host=None,
                cable_type=cable_type
            )

        finally:
            config_interface_admin_status(upper_tor_host, active_active_ports, "up")
            upper_tor_host.shell("config save -y")
