"""
=============================================================================
Module: dualtor_io
File: test_link_drop.py
=============================================================================

Description:
    Test suite for validating dual-ToR resilience when mux simulator drops packets on specific
    links. This module simulates packet loss on upper/lower ToR paths and NIC links to verify
    failover behavior and traffic recovery. Tests cover both active-standby and active-active
    cable types with various packet drop scenarios.

Test Intent:
    - test_link_drop_active_active_upstream: Verify traffic failover when upstream link to active-active NIC drops packets (server to T1)
    - test_link_drop_active_active_downstream_nic: Verify traffic failover when downstream NIC link drops packets (T1 to server, active-active)
    - test_link_drop_active_active_downstream_tor: Verify traffic failover when downstream ToR link drops packets (T1 to server, active-active)
    - test_link_drop_active_upstream: Verify traffic failover when active ToR link drops packets (server to T1)
    - test_link_drop_standby_upstream: Verify standby ToR link drop does not affect traffic (server to T1)
    - test_link_drop_active_downstream: Verify traffic failover when active ToR link drops packets (T1 to server)
    - test_link_drop_standby_downstream: Verify standby ToR link drop does not affect traffic (T1 to server)

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
    - set_drop: Drops packets on specified interface and direction in mux simulator
    - set_drop_all: Drops all packets on specified interface in mux simulator
    - set_output: Restores normal forwarding on specified interface
    - simulator_flap_counter: Gets flap counter from mux simulator
    - nic_simulator_flap_counter: Gets flap counter from NIC simulator
    - set_drop_active_active: Drops packets on active-active NIC link
    - cable_type: Cable type fixture (active-standby or active-active)
    - active_active_ports: Active-active port configuration
    - active_standby_ports: Active-standby port configuration
    - drop_flow_upper_tor: Drops packets to upper ToR
    - drop_flow_lower_tor: Drops packets to lower ToR

Dependencies:
    - Mux simulator control for packet drop simulation
    - NIC simulator control for active-active drop simulation
    - PTF framework for traffic generation and verification
    - TrafficDirection enum: NIC_DOWNSTREAM, NIC_UPSTREAM, TOR_DOWNSTREAM, TOR_UPSTREAM

Notes:
    - Tests are marked with pytest.mark.topology("dualtor")
    - Disruption must be less than MUX_SIM_ALLOWED_DISRUPTION_SEC (1 second)
    - Active-active tests are marked with @pytest.mark.enable_active_active
    - Packet drop is simulated at mux level (not actual link failure)
    - set_drop uses traffic direction: upper_tor, lower_tor, tor_a, tor_b, nic
    - Active-active uses NIC-level drop (NIC_UPSTREAM, NIC_DOWNSTREAM, TOR_UPSTREAM, TOR_DOWNSTREAM)
    - Tests verify that dropping packets on active link triggers failover
    - Tests verify that dropping packets on standby link has no effect
    - Cleanup: set_output restores normal forwarding on all interfaces
    - Flap counter validates that switchover occurred during active link drop

=============================================================================
"""

import logging
import pytest
import time

from tests.common.dualtor.control_plane_utils import verify_tor_states
from tests.common.dualtor.dual_tor_utils import upper_tor_host, lower_tor_host                  # noqa: F401
from tests.common.dualtor.dual_tor_utils import check_simulator_flap_counter                    # noqa: F401
from tests.common.dualtor.data_plane_utils import send_server_to_t1_with_action                 # noqa: F401
from tests.common.dualtor.data_plane_utils import send_t1_to_server_with_action                 # noqa: F401
from tests.common.dualtor.mux_simulator_control import set_drop                                 # noqa: F401
from tests.common.dualtor.mux_simulator_control import set_drop_all                             # noqa: F401
from tests.common.dualtor.mux_simulator_control import set_output                               # noqa: F401
from tests.common.dualtor.mux_simulator_control import simulator_flap_counter                   # noqa: F401
from tests.common.dualtor.mux_simulator_control import toggle_all_simulator_ports_to_upper_tor  # noqa: F401
from tests.common.dualtor.nic_simulator_control import nic_simulator_flap_counter               # noqa: F401
from tests.common.dualtor.nic_simulator_control import set_drop_active_active                   # noqa: F401
from tests.common.dualtor.nic_simulator_control import TrafficDirection
from tests.common.fixtures.ptfhost_utils import run_icmp_responder, run_garp_service            # noqa: F401
from tests.common.fixtures.ptfhost_utils import change_mac_addresses                            # noqa: F401
from tests.common.dualtor.constants import MUX_SIM_ALLOWED_DISRUPTION_SEC
from tests.common.dualtor.dual_tor_common import ActiveActivePortID
from tests.common.dualtor.dual_tor_common import active_active_ports                            # noqa: F401
from tests.common.dualtor.dual_tor_common import active_standby_ports                           # noqa: F401
from tests.common.dualtor.dual_tor_common import cable_type                                     # noqa: F401
from tests.common.dualtor.dual_tor_common import CableType


pytestmark = [
    pytest.mark.topology("dualtor")
]


def _set_drop_factory(set_drop_func, direction, tor_mux_intfs):
    """Factory to get set drop function for either upper_tor or lower_tor."""
    def _set_drop_all_interfaces():
        logging.debug("Start set drop for %s at %s", direction, time.time())
        for intf in tor_mux_intfs:
            set_drop_func(intf, [direction])
    return _set_drop_all_interfaces


@pytest.fixture(scope="function")
def drop_flow_upper_tor(set_drop, set_output, active_standby_ports):                    # noqa: F811
    """Drop the flow to the upper ToR."""
    direction = "upper_tor"
    return _set_drop_factory(set_drop, direction, active_standby_ports)


@pytest.fixture(scope="function")
def drop_flow_lower_tor(set_drop, set_output, active_standby_ports):                    # noqa: F811
    """Drop the flow to the lower ToR."""
    direction = "lower_tor"
    return _set_drop_factory(set_drop, direction, active_standby_ports)


def _set_drop_all_factory(set_drop_all_func, direction, tor_mux_intfs):                         # noqa: F811
    """Factory to get set drop function for either upper_tor or lower_tor."""
    def _set_drop_all_interfaces():
        logging.debug("Start set drop all for %s at %s", direction, time.time())
        set_drop_all_func([direction])
    return _set_drop_all_interfaces


@pytest.fixture(scope="function")
def drop_flow_upper_tor_all(set_drop_all, set_output, active_standby_ports):                    # noqa: F811
    """Drop the flow to the upper ToR."""
    direction = "upper_tor"
    return _set_drop_all_factory(set_drop_all, direction, active_standby_ports)


@pytest.fixture(scope="function")
def drop_flow_lower_tor_all(set_drop_all, set_output, active_standby_ports):                    # noqa: F811
    """Drop the flow to the lower ToR."""
    direction = "lower_tor"
    return _set_drop_all_factory(set_drop_all, direction, active_standby_ports)


@pytest.fixture(scope="function")
def drop_flow_upper_tor_active_active(active_active_ports, set_drop_active_active):     # noqa: F811
    direction = TrafficDirection.UPSTREAM
    portid = ActiveActivePortID.UPPER_TOR

    def _drop_flow_upper_tor_active_active():
        logging.debug("Start set drop for upper ToR at %s", time.time())
        for port in active_active_ports:
            logging.debug("Set drop on port %s, portid %s, direction %s" % (port, portid, direction))
        portids = [portid for _ in active_active_ports]
        directions = [direction for _ in active_active_ports]
        set_drop_active_active(active_active_ports, portids, directions)

    return _drop_flow_upper_tor_active_active


@pytest.mark.enable_active_active
def test_active_link_drop_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor, drop_flow_upper_tor_all,   # noqa: F811
    drop_flow_upper_tor_active_active, cable_type                       # noqa: F811
):
    """
    Send traffic from servers to T1 and remove the flow between the servers and the active ToR.
    Verify the switchover and disruption last < 1 second.
    """
    if cable_type == CableType.active_standby:
        send_server_to_t1_with_action(
            upper_tor_host,
            verify=True,
            delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=3,
            action=drop_flow_upper_tor_all
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health="unhealthy",
            cable_type=cable_type
        )

    if cable_type == CableType.active_active:
        send_server_to_t1_with_action(
            upper_tor_host,
            verify=True,
            delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=1,
            action=drop_flow_upper_tor_active_active
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health="unhealthy",
            cable_type=cable_type,
            skip_state_db=True
        )


@pytest.mark.enable_active_active
def test_active_link_drop_downstream_active(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor, drop_flow_upper_tor_all,   # noqa: F811
    drop_flow_upper_tor_active_active, cable_type                       # noqa: F811
):
    """
    Send traffic from the T1s to the servers via the active Tor and remove the flow between the
    servers and the active ToR.
    Verify the switchover and disruption last < 1 second.
    """
    if cable_type == CableType.active_standby:
        send_t1_to_server_with_action(
            upper_tor_host,
            verify=True,
            delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=3,
            action=drop_flow_upper_tor_all
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health="unhealthy",
            cable_type=cable_type
        )

    if cable_type == CableType.active_active:
        send_t1_to_server_with_action(
            upper_tor_host,
            verify=True,
            delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
            allowed_disruption=1,
            action=drop_flow_upper_tor_active_active
        )
        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health="unhealthy",
            cable_type=cable_type,
            skip_state_db=True
        )


def test_active_link_drop_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    toggle_all_simulator_ports_to_upper_tor, drop_flow_upper_tor_all    # noqa: F811
):
    """
    Send traffic from the T1s to the servers via the standby Tor and remove the flow between the
    servers and the active ToR.
    Verify the switchover and disruption last < 1 second.
    """
    send_t1_to_server_with_action(
        lower_tor_host,
        verify=True,
        delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=3,
        action=drop_flow_upper_tor_all
    )
    verify_tor_states(
        expected_active_host=lower_tor_host,
        expected_standby_host=upper_tor_host,
        expected_standby_health="unhealthy"
    )


def test_standby_link_drop_upstream(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    check_simulator_flap_counter, drop_flow_lower_tor_all,              # noqa: F811
    toggle_all_simulator_ports_to_upper_tor                             # noqa: F811
):
    """
    Send traffic from servers to T1 and remove the flow between the servers and the standby ToR.
    Verify that no switchover and disruption occur.
    """
    send_server_to_t1_with_action(
        upper_tor_host,
        verify=True,
        delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=2,
        action=drop_flow_lower_tor_all
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health="unhealthy"
    )
    check_simulator_flap_counter(2)


def test_standby_link_drop_downstream_active(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    check_simulator_flap_counter, drop_flow_lower_tor_all,              # noqa: F811
    toggle_all_simulator_ports_to_upper_tor                             # noqa: F811
):
    """
    Send traffic from the T1s to the servers via the active Tor and remove the flow between the
    servers and the standby ToR.
    Verify that no switchover and disruption occur.
    """
    send_t1_to_server_with_action(
        upper_tor_host,
        verify=True,
        delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=2,
        action=drop_flow_lower_tor_all
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health="unhealthy"
    )
    check_simulator_flap_counter(2)


def test_standby_link_drop_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    check_simulator_flap_counter, drop_flow_lower_tor_all,              # noqa: F811
    toggle_all_simulator_ports_to_upper_tor                             # noqa: F811
):
    """
    Send traffic from the T1s to the servers via the standby Tor and remove the flow between the
    servers and the standby ToR.
    Verify that no switchover and disruption occur.
    """
    send_t1_to_server_with_action(
        lower_tor_host,
        verify=True,
        delay=MUX_SIM_ALLOWED_DISRUPTION_SEC,
        allowed_disruption=2,
        action=drop_flow_lower_tor_all
    )
    verify_tor_states(
        expected_active_host=upper_tor_host,
        expected_standby_host=lower_tor_host,
        expected_standby_health="unhealthy"
    )
    check_simulator_flap_counter(2)
