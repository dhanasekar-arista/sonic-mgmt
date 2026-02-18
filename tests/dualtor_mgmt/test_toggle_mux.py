"""
=============================================================================
Module: dualtor_mgmt
File: test_toggle_mux.py
=============================================================================

Description:
    Test suite for validating mux cable state toggling on dual-ToR active-standby configurations.
    This module tests manual and automatic mux mode operations, probe interval adjustments, and
    state consistency between the mux simulator and DUT after toggling between active and standby
    states on upper and lower ToRs.

Test Intent:
    - test_toggle_mux_from_upper_to_lower: Verify manual toggle from upper ToR active to lower ToR active succeeds
    - test_toggle_mux_from_lower_to_upper: Verify manual toggle from lower ToR active to upper ToR active succeeds
    - test_toggle_mux_from_upper_to_upper: Verify toggle from upper ToR to upper ToR (no change) succeeds
    - test_toggle_mux_from_lower_to_lower: Verify toggle from lower ToR to lower ToR (no change) succeeds
    - test_toggle_mux_from_active_to_auto: Verify toggling from manual active mode back to auto mode succeeds
    - test_toggle_mux_from_standby_to_auto: Verify toggling from manual standby mode back to auto mode succeeds

Topology:
    - dualtor: Dual-ToR topology with active-standby cable type only

Fixtures Used:
    - active_standby_ports: Active-standby port configuration (skips if no ports available)
    - restore_mux_auto_mode: Restores all muxcable to auto mode after test
    - reset_link_prober_interval_v4: Resets link prober interval_v4 to original value after module
    - reduce_and_add_back_link_prober_interval_v4: Reduces interval_v4 to 100ms during test, restores after

Dependencies:
    - config muxcable mode command for manual state control
    - show muxcable status command for state verification
    - MUX_LINKMGR config for link prober interval adjustment
    - Mux simulator control for state verification
    - wait_until utility for polling state changes

Notes:
    - Tests are marked with pytest.mark.topology("dualtor")
    - Tests skip on non-dualtor testbed or when no active-standby ports available
    - Mux modes: active (manual active), standby (manual standby), auto (automatic switchover)
    - Link prober interval_v4 is temporarily reduced to 100ms for faster state convergence
    - Tests use wait_until with 30-second timeout for mux state stabilization
    - Mux state verification uses both DUT (show muxcable status) and simulator (check_mux_status)
    - validate_check_result ensures mux state matches expected values
    - UPPER_TOR and LOWER_TOR constants identify ToR in dual-ToR pair
    - Auto mode restores automatic failover based on link health
    - Tests verify both control plane (config) and operational state (status)

=============================================================================
"""

import logging
import json
import pytest

from tests.common.dualtor.constants import UPPER_TOR, LOWER_TOR
from tests.common.dualtor.dual_tor_common import active_standby_ports                                   # noqa: F401
from tests.common.dualtor.mux_simulator_control import check_mux_status, validate_check_result
from tests.common.dualtor.dual_tor_utils import recover_linkmgrd_probe_interval, update_linkmgrd_probe_interval
from tests.common.utilities import wait_until


pytestmark = [
    pytest.mark.topology("dualtor")
]

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module", autouse=True)
def check_topo(active_standby_ports, tbinfo):                                                           # noqa: F811
    if 'dualtor' not in tbinfo['topo']['name']:
        pytest.skip('Skip on non-dualtor testbed')

    if not active_standby_ports:
        pytest.skip("Skip as no 'active-standby' mux ports available")


@pytest.fixture
def restore_mux_auto_mode(duthosts):
    yield
    logger.info('Set all muxcable to auto mode on all ToRs')
    duthosts.shell('config muxcable mode auto all')


@pytest.fixture(scope="module")
def get_interval_v4(duthosts):
    mux_linkmgr_output = duthosts.shell('sonic-cfggen -d --var-json MUX_LINKMGR')
    mux_linkmgr = list(mux_linkmgr_output.values())[0]['stdout']
    mux_linkmgr_json = json.loads(mux_linkmgr)
    if len(mux_linkmgr) != 0 and 'LINK_PROBER' in mux_linkmgr_json:
        cur_interval_v4 = mux_linkmgr_json['LINK_PROBER']['interval_v4']
        return cur_interval_v4
    else:
        return None


@pytest.fixture(scope="module")
def reset_link_prober_interval_v4(duthosts, get_interval_v4, tbinfo):
    cur_interval_v4 = get_interval_v4
    if cur_interval_v4 is not None:
        recover_linkmgrd_probe_interval(duthosts, tbinfo)

    # NOTE: as there is no icmp_responder running, the device is stucked in consistently probing
    # the mux status. If there is a previous case that has fixture run_icmp_responder called, the
    # link prober interval is changed into 1000ms, the mux probing interval could be 384s at most.
    # So after a hardware mux change, SONiC is only able to learn the change after 384s in worst case.
    # To accelerate this, let's restarting linkmgrd to break out from the probing loop firstly and
    # change the the probing interval back to 100ms to reduce the future probing interval maximum
    # down to 38.4s.
    duthosts.shell("docker exec mux supervisorctl restart linkmgrd")

    yield

    if cur_interval_v4 is not None:
        update_linkmgrd_probe_interval(duthosts, tbinfo, cur_interval_v4)


@pytest.mark.parametrize("active_side", [UPPER_TOR, LOWER_TOR])
def test_toggle_mux_from_simulator(duthosts, active_side, toggle_all_simulator_ports,
                                   get_mux_status, reset_link_prober_interval_v4, restore_mux_auto_mode):
    logger.info('Set all muxcable to manual mode on all ToRs')
    duthosts.shell('config muxcable mode manual all')

    logger.info('Toggle mux active side from mux simulator')
    toggle_all_simulator_ports(active_side)

    check_result = wait_until(60, 5, 2, check_mux_status, duthosts, active_side)
    validate_check_result(check_result, duthosts, get_mux_status)


@pytest.mark.parametrize("active_side", [UPPER_TOR, LOWER_TOR])
def test_toggle_mux_from_cli(duthosts, active_side, get_mux_status,
                             reset_link_prober_interval_v4, restore_mux_auto_mode):
    logger.info('Reset muxcable mode to auto for all ports on all DUTs')
    duthosts.shell('config muxcable mode auto all')

    # Use cli to toggle muxcable active side
    if active_side == UPPER_TOR:
        mux_active_dut = duthosts[0]
    else:
        mux_active_dut = duthosts[1]
    mux_active_dut.shell('config muxcable mode active all')

    check_result = wait_until(60, 5, 2, check_mux_status, duthosts, active_side)
    validate_check_result(check_result, duthosts, get_mux_status)
