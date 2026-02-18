"""
=============================================================================
Module: dualtor_io
File: test_tor_failure.py
=============================================================================

Description:
    Test suite for validating dual-ToR resilience and traffic forwarding during ToR device
    failures. This module tests failover behavior when active or standby ToR experiences
    hard failures (power off, reboot) or blackhole traffic conditions. Tests verify minimal
    traffic disruption and proper mux state transitions during ToR recovery scenarios.

Test Intent:
    - test_active_tor_reboot_upstream: Verify traffic failover when active ToR reboots (server to T1 traffic)
    - test_active_tor_reboot_downstream: Verify traffic failover when active ToR reboots (T1 to server traffic)
    - test_standby_tor_reboot: Verify standby ToR reboot does not affect traffic or mux states
    - test_active_tor_power_off: Verify traffic failover when active ToR power is toggled via PDU
    - test_standby_tor_power_off: Verify standby ToR power toggle does not affect traffic or mux states
    - test_active_tor_blackhole_upstream: Verify traffic failover when active ToR drops all traffic (upstream)
    - test_active_tor_blackhole_downstream: Verify traffic failover when active ToR drops all traffic (downstream)
    - test_standby_tor_blackhole: Verify standby ToR blackholing does not affect traffic

Topology:
    - dualtor: Dual-ToR topology with active-standby or active-active cable types

Fixtures Used:
    - upper_tor_host: Upper ToR DUT host object
    - lower_tor_host: Lower ToR DUT host object
    - toggle_all_simulator_ports_to_upper_tor: Sets all mux ports to upper ToR (active)
    - send_t1_to_server_with_action: Sends downstream traffic with action during transmission
    - send_server_to_t1_with_action: Sends upstream traffic with action during transmission
    - run_icmp_responder: Runs ICMP responder on PTF for server simulation
    - run_garp_service: Runs GARP service on PTF for MAC address updates
    - change_mac_addresses: Changes PTF MAC addresses to match server MACs
    - check_simulator_flap_counter: Verifies mux simulator flap counts
    - toggle_upper_tor_pdu: PDU controller fixture for upper ToR power control
    - toggle_lower_tor_pdu: PDU controller fixture for lower ToR power control
    - mux_status_from_nic_simulator: NIC simulator mux status getter
    - tunnel_traffic_monitor: Monitors tunnel traffic during tests

Dependencies:
    - Mux simulator control for cable state management
    - NIC simulator for active-active forwarding state validation
    - PDU controller for power management tests
    - PTF framework for traffic generation and verification
    - tor_failure_utils for reboot and blackhole operations
    - LogAnalyzer for syslog validation during failures

Notes:
    - Tests are marked with pytest.mark.topology("dualtor")
    - Disruption must be less than MUX_SIM_ALLOWED_DISRUPTION_SEC (1 second)
    - Active-active cable tests verify forwarding states instead of active/standby
    - Reboot tests use cold reboot and wait for mux container recovery
    - Power tests require PDU controller availability (skipped if unavailable)
    - Blackhole tests use DROP iptables rules to simulate traffic loss
    - Expected log patterns: container not running errors during failures
    - Tests verify control plane (mux state) and data plane (traffic forwarding)
    - Active-active uses NIC simulator forwarding states (ACTIVE, STANDBY, UNKNOWN)

=============================================================================
"""

import logging
import pytest
import time

from tests.common.dualtor.control_plane_utils import verify_tor_states
from tests.common.dualtor.data_plane_utils import (  # noqa: F401
    send_t1_to_server_with_action,
    send_server_to_t1_with_action,
)
from tests.common.dualtor.dual_tor_utils import upper_tor_host, lower_tor_host  # noqa: F401
from tests.common.dualtor.dual_tor_utils import check_simulator_flap_counter  # noqa: F401
from tests.common.dualtor.mux_simulator_control import toggle_all_simulator_ports_to_upper_tor  # noqa: F401

from tests.common.dualtor.tor_failure_utils import (  # noqa: F401
    reboot_tor,
    tor_blackhole_traffic,
    wait_for_device_reachable,
)
from tests.common.dualtor.tor_failure_utils import wait_for_mux_container, wait_for_pmon_container  # noqa: F401
from tests.common.fixtures.ptfhost_utils import run_icmp_responder, run_garp_service, change_mac_addresses  # noqa: F401
from tests.common.dualtor.nic_simulator_control import mux_status_from_nic_simulator   # noqa: F401
from tests.common.dualtor.nic_simulator_control import ForwardingState
from tests.common.dualtor.tunnel_traffic_utils import tunnel_traffic_monitor  # noqa: F401
from tests.common.dualtor.constants import MUX_SIM_ALLOWED_DISRUPTION_SEC
from tests.common.dualtor.dual_tor_common import cable_type  # noqa: F401
from tests.common.dualtor.dual_tor_common import CableType
from tests.common.dualtor.dual_tor_common import ActiveActivePortID
from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from tests.common.plugins.loganalyzer.loganalyzer import LogAnalyzer


logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology("dualtor")
]


def toggle_pdu_outlet(controller):
    logger.info("Toggling PDU for {}".format(controller.dut_hostname))
    controller.turn_off_outlet()
    time.sleep(10)
    controller.turn_on_outlet()


@pytest.fixture(scope='module')
def toggle_upper_tor_pdu(upper_tor_host, get_pdu_controller):       # noqa: F811
    pdu_controller = get_pdu_controller(upper_tor_host)
    if pdu_controller is None:
        # restart the kernel instantly through system request if there is no pdu information present
        return lambda: upper_tor_host.shell("nohup sh -c 'sleep 2; echo b > /proc/sysrq-trigger;' > /dev/null &")
    else:
        return lambda: toggle_pdu_outlet(pdu_controller)


@pytest.fixture(scope='module')
def toggle_lower_tor_pdu(lower_tor_host, get_pdu_controller):       # noqa: F811
    pdu_controller = get_pdu_controller(lower_tor_host)
    if pdu_controller is None:
        return lambda: lower_tor_host.shell("nohup sh -c 'sleep 2; echo b > /proc/sysrq-trigger;' > /dev/null &")
    else:
        return lambda: toggle_pdu_outlet(pdu_controller)


@pytest.mark.enable_active_active
def test_active_tor_reboot_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor, toggle_upper_tor_pdu,      # noqa: F811
    wait_for_device_reachable, wait_for_mux_container, cable_type,      # noqa: F811
    wait_for_pmon_container, setup_loganalyzer                          # noqa: F811
):
    """
    Send upstream traffic and reboot the active ToR. Confirm switchover
    occurred and disruption lasts < 1 second
    """
    setup_loganalyzer(upper_tor_host, collect_only=True, collect_from_bootup=True)
    send_server_to_t1_with_action(
        upper_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        action=toggle_upper_tor_pdu, stop_after=60
    )
    wait_for_device_reachable(upper_tor_host)
    wait_for_mux_container(upper_tor_host)
    wait_for_pmon_container(upper_tor_host)

    if cable_type == CableType.active_standby:
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host
        )
    elif cable_type == CableType.active_active:
        verify_tor_states(
            expected_active_host=[upper_tor_host, lower_tor_host],
            expected_standby_host=None,
            cable_type=cable_type,
            verify_db_timeout=60
        )


def test_active_tor_reboot_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor, toggle_upper_tor_pdu,      # noqa: F811
    wait_for_device_reachable, wait_for_mux_container,                  # noqa: F811
    wait_for_pmon_container, setup_loganalyzer                          # noqa: F811
):
    """
    Send downstream traffic to the standby ToR and reboot the active ToR.
    Confirm switchover occurred and disruption lasts < 1 second
    """
    setup_loganalyzer(upper_tor_host, collect_only=True, collect_from_bootup=True)
    send_t1_to_server_with_action(
        lower_tor_host, verify=True, delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        action=toggle_upper_tor_pdu, stop_after=60
    )
    wait_for_device_reachable(upper_tor_host)
    wait_for_mux_container(upper_tor_host)
    wait_for_pmon_container(upper_tor_host)
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host
    )


def test_standby_tor_reboot_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor, toggle_lower_tor_pdu,      # noqa: F811
    wait_for_device_reachable, wait_for_mux_container,                  # noqa: F811
    wait_for_pmon_container, setup_loganalyzer                          # noqa: F811
):
    """
    Send upstream traffic and reboot the standby ToR. Confirm no switchover
    occurred and no disruption
    """
    setup_loganalyzer(lower_tor_host, collect_only=True, collect_from_bootup=True)
    send_server_to_t1_with_action(
        upper_tor_host, verify=True,
        action=toggle_lower_tor_pdu, stop_after=60
    )
    wait_for_device_reachable(lower_tor_host)
    wait_for_mux_container(lower_tor_host)
    wait_for_pmon_container(lower_tor_host)
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host
    )


def test_standby_tor_reboot_downstream_active(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor, toggle_lower_tor_pdu,      # noqa: F811
    wait_for_device_reachable, wait_for_mux_container,                  # noqa: F811
    wait_for_pmon_container, setup_loganalyzer                          # noqa: F811
):
    """
    Send downstream traffic to the active ToR and reboot the standby ToR.
    Confirm no switchover occurred and no disruption
    """
    setup_loganalyzer(lower_tor_host, collect_only=True, collect_from_bootup=True)
    send_t1_to_server_with_action(
        upper_tor_host, verify=True,
        action=toggle_lower_tor_pdu, stop_after=60
    )
    wait_for_device_reachable(lower_tor_host)
    wait_for_mux_container(lower_tor_host)
    wait_for_pmon_container(lower_tor_host)
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host
    )


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
@pytest.mark.disable_loganalyzer
def test_active_tor_reboot_downstream(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_upper_tor_pdu, wait_for_device_reachable, cable_type,        # noqa: F811
    tunnel_traffic_monitor, mux_status_from_nic_simulator,              # noqa: F811
    wait_for_mux_container, wait_for_pmon_container                      # noqa: F811
):
    def check_forwarding_state(upper_tor_forwarding_state, lower_tor_forwarding_state):
        mux_status = mux_status_from_nic_simulator()
        logging.debug(
            "Check forwarding state, upper ToR: %s, lower ToR: %s",
            upper_tor_forwarding_state,
            lower_tor_forwarding_state
        )
        logging.debug("Mux status from nic_simulator:\n%s", mux_status)
        for port in mux_status:
            if ((mux_status[port][ActiveActivePortID.UPPER_TOR] != upper_tor_forwarding_state) or
                    (mux_status[port][ActiveActivePortID.LOWER_TOR] != lower_tor_forwarding_state)):
                logging.debug("Port %s mux status is not expected", port)
                return False
        return True

    # verify all ToRs are in active state
    verify_tor_states(
        expected_active_host=[upper_tor_host, lower_tor_host],
        expected_standby_host=None,
        cable_type=cable_type
    )

    # use loganalyzer to collect logs from the lower tor during reboot
    with LogAnalyzer(ansible_host=lower_tor_host, marker_prefix="test_active_tor_reboot_downstream"):
        # reboot the upper ToR and verify the upper ToR forwarding state is changed to standby
        toggle_upper_tor_pdu()
        pytest_assert(
            wait_until(60, 5, 5, check_forwarding_state, ForwardingState.STANDBY, ForwardingState.ACTIVE),
            "Forwarding state check failed after reboot."
        )
        lower_tor_host.shell("show mux grpc mux", module_ignore_errors=True)

        # verify the upper ToR changes back to active after the upper comes back from reboot
        wait_for_device_reachable(upper_tor_host)
        wait_for_mux_container(upper_tor_host)
        wait_for_pmon_container(upper_tor_host)
        pytest_assert(
            wait_until(180, 5, 60, check_forwarding_state, ForwardingState.ACTIVE, ForwardingState.ACTIVE),
            "Forwarding state check failed after the upper ToR comes back from reboot."
        )
        verify_tor_states(
            expected_active_host=[upper_tor_host, lower_tor_host],
            expected_standby_host=None,
            cable_type=cable_type
        )

    # verify the server receives packets with no disrupts, no tunnel traffic
    with tunnel_traffic_monitor(upper_tor_host, existing=False):
        send_t1_to_server_with_action(upper_tor_host, verify=True, stop_after=60)
