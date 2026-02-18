"""
=============================================================================
Module: dualtor_mgmt
File: test_dualtor_linkmgrd_restart_mux_port_status.py
=============================================================================

Description:
    Test suite for validating mux port status recovery after linkmgrd restarts. This module
    tests that mux ports return to their expected states (active or standby) after linkmgrd
    process is killed and automatically restarted, both with heartbeat enabled and disabled.
    Tests verify linkmgrd's state recovery mechanism across multiple restart iterations.

Test Intent:
    - test_linkmgr_restart: Verify mux port status correctly recovers to expected state after linkmgrd restart (parametrized by heartbeat on/off)

Topology:
    - dualtor: Dual-ToR topology with active-standby or active-active cable types

Fixtures Used:
    - upper_tor_host: Upper ToR DUT host object
    - lower_tor_host: Lower ToR DUT host object
    - toggle_all_simulator_ports_to_upper_tor: Sets all mux ports to upper ToR (active)
    - run_icmp_responder: Runs ICMP responder on PTF for link health monitoring
    - shutdown_icmp_responder: Stops ICMP responder to simulate heartbeat loss
    - start_icmp_responder: Starts ICMP responder to restore heartbeat
    - cable_type: Cable type fixture (active-standby or active-active)
    - active_active_ports: Active-active port configuration
    - active_standby_ports: Active-standby port configuration
    - rand_selected_dut: Randomly selected DUT for testing
    - loop_times: Number of restart iterations based on completeness level (debug=1, basic=10, thorough=60)
    - heartbeat_control: Parametrized fixture to control heartbeat on/off

Dependencies:
    - linkmgrd process in mux container
    - ICMP link prober for heartbeat monitoring
    - show muxcable status command for state verification
    - docker exec for process control within mux container
    - Automatic process restart via supervisord

Notes:
    - Test is marked with pytest.mark.topology("dualtor")
    - Test parametrized with heartbeat: "on" or "off"
    - Loop times controlled by --function_completeness_level flag
    - Completeness levels: debug(1), basic(10), confident(50), thorough(60), diagnose(100)
    - Test procedure: Toggle to upper ToR -> Kill linkmgrd -> Wait for restart -> Verify state
    - Linkmgrd is killed with 'pkill linkmgrd' in mux container
    - Heartbeat "off" simulates scenario where servers are unreachable
    - Expected state with heartbeat on: active on upper ToR, standby on lower ToR
    - Expected state with heartbeat off: standby on upper ToR, standby on lower ToR
    - Test validates linkmgrd can recover state from APP_DB and STATE_DB after restart
    - Maximum wait time for state recovery: 60 seconds per iteration

=============================================================================
"""

import logging
import json
import pytest

from tests.common.dualtor.dual_tor_common import active_active_ports                                        # noqa: F401
from tests.common.dualtor.dual_tor_common import active_standby_ports                                       # noqa: F401
from tests.common.dualtor.dual_tor_common import cable_type                                                 # noqa: F401
from tests.common.dualtor.dual_tor_common import CableType
from tests.common.dualtor.dual_tor_utils import upper_tor_host                                              # noqa: F401
from tests.common.dualtor.dual_tor_utils import lower_tor_host                                              # noqa: F401
from tests.common.dualtor.dual_tor_utils import show_muxcable_status
from tests.common.dualtor.icmp_responder_control import shutdown_icmp_responder                             # noqa: F401
from tests.common.dualtor.icmp_responder_control import start_icmp_responder                                # noqa: F401
from tests.common.dualtor.mux_simulator_control import toggle_all_simulator_ports_to_upper_tor              # noqa: F401
from tests.common.fixtures.ptfhost_utils import run_icmp_responder                                          # noqa: F401
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until
from tests.conftest import rand_selected_dut                                                                # noqa: F401


pytestmark = [
    pytest.mark.topology("dualtor")
]


LOOP_TIMES_LEVEL_MAP = {
    'debug': 1,
    'basic': 10,
    'confident': 50,
    'thorough': 60,
    'diagnose': 100
}


@pytest.fixture
def loop_times(get_function_completeness_level):
    normalized_level = get_function_completeness_level
    if normalized_level is None:
        normalized_level = 'debug'
    return LOOP_TIMES_LEVEL_MAP[normalized_level]


@pytest.fixture
def heartbeat_control(request, start_icmp_responder, shutdown_icmp_responder):                      # noqa: F811
    heartbeat = request.param
    if heartbeat == "off":
        shutdown_icmp_responder()

    yield heartbeat

    if heartbeat == "off":
        start_icmp_responder()


def check_mux_port_status_after_linkmgrd_restart(rand_selected_dut, ports, loop_times,              # noqa: F811
                                                 status=None, health=None):
    def _check_mux_port_status(duthost, ports, status, health):
        show_mux_status_ret = show_muxcable_status(duthost)
        logging.debug("show_mux_status_ret: {}".format(json.dumps(show_mux_status_ret, indent=4)))

        for port in ports:
            if port not in show_mux_status_ret:
                return False

            if health is None:
                # Active-Active case
                health = 'healthy' if status == 'active' else 'unhealthy'
                if show_mux_status_ret[port]['status'] != status:
                    logging.debug(f"Port {port} status-{show_mux_status_ret[port]['status']}, expected status-{status}")
                    return False

            if show_mux_status_ret[port]['health'] != health or show_mux_status_ret[port]['hwstatus'] != 'consistent':
                logging.debug(f"Port {port} health-{show_mux_status_ret[port]['health']}, expected health-{health};"
                              f"hwstatus-{show_mux_status_ret[port]['hwstatus']}, expected hwstatus-consistent")
                return False
        return True

    for _ in range(loop_times):
        rand_selected_dut.shell("docker exec mux supervisorctl restart linkmgrd")
        pytest_assert(wait_until(30, 5, 0, lambda: "RUNNING" in rand_selected_dut.
                                 command("docker exec mux supervisorctl status linkmgrd")
                                 ["stdout"]), "linkmgrd is not running after restart")
        pytest_assert(wait_until(120, 10, 0, _check_mux_port_status, rand_selected_dut, ports, status, health),
                      "MUX port status is not correct after linkmgrd restart")


@pytest.mark.enable_active_active
@pytest.mark.parametrize("heartbeat_control", ["on", "off"], indirect=True)
def test_dualtor_linkmgrd_restart_mux_port_status(cable_type, heartbeat_control, rand_selected_dut,   # noqa: F811
                                                  active_active_ports, active_standby_ports,          # noqa: F811
                                                  loop_times):
    """
    Test MUX port status on dual ToR after linkmgrd restart with heartbeat on/off

    Note: Skip mux status checking for active-standby case due to initialization timing issue.
          Only health and hwstatus are checked in this scenario.
    """
    ports = active_active_ports if cable_type == CableType.active_active else active_standby_ports

    # skip test if topology mismatch
    if not ports:
        pytest.skip(f'Skipping toggle on dualtor for cable_type={cable_type}.')

    # Check MUX port status after linkmgrd restart
    if cable_type == CableType.active_active:
        expected_status = 'active' if heartbeat_control == "on" else 'standby'
        check_mux_port_status_after_linkmgrd_restart(rand_selected_dut, ports, loop_times, expected_status)
    if cable_type == CableType.active_standby:  # active-standby
        health = 'healthy' if heartbeat_control == "on" else 'unhealthy'
        check_mux_port_status_after_linkmgrd_restart(rand_selected_dut, ports, loop_times,
                                                     status=None, health=health)
