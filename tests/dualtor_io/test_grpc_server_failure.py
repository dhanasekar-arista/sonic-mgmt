"""
=============================================================================
Module: dualtor_io
File: test_grpc_server_failure.py
=============================================================================

Description:
    Test suite for validating active-active dual-ToR behavior during gRPC server failures.
    This module tests control plane (mux mode changes) and data plane (traffic forwarding)
    resilience when the NIC simulator's gRPC server is stopped, simulating communication
    loss between ToR and SmartNIC. Tests verify graceful degradation and recovery.

Test Intent:
    - test_grpc_server_failure_config_standby_config_auto_upstream_active: Verify mux mode transitions work correctly when gRPC server is down (standby->auto)
    - test_grpc_server_failure_upstream_active: Verify upstream traffic continues with zero disruption when gRPC server fails (server to T1)
    - test_grpc_server_failure_downstream_active: Verify downstream traffic continues with zero disruption when gRPC server fails (T1 to server)
    - test_grpc_server_restart_upstream_active: Verify traffic continues with zero disruption when gRPC server restarts (server to T1)
    - test_grpc_server_restart_downstream_active: Verify traffic continues with zero disruption when gRPC server restarts (T1 to server)

Topology:
    - dualtor: Dual-ToR topology with active-active cable type only

Fixtures Used:
    - upper_tor_host: Upper ToR DUT host object
    - lower_tor_host: Lower ToR DUT host object
    - send_t1_to_server_with_action: Sends downstream traffic with action during transmission
    - send_server_to_t1_with_action: Sends upstream traffic with action during transmission
    - run_icmp_responder: Runs ICMP responder on PTF for server simulation
    - run_garp_service: Runs GARP service on PTF for MAC address updates
    - change_mac_addresses: Changes PTF MAC addresses to match server MACs
    - cable_type: Cable type fixture (must be active-active)
    - active_active_ports: Active-active port configuration
    - stop_nic_grpc_server: Stops NIC simulator gRPC server
    - restart_nic_simulator: Restarts NIC simulator

Dependencies:
    - NIC simulator control for gRPC server management
    - PTF framework for traffic generation and verification
    - config mux mode command for mux state manipulation
    - Active-active cable type hardware

Notes:
    - Tests are marked with @pytest.mark.enable_active_active
    - Tests are marked with @pytest.mark.skip_active_standby (only for active-active)
    - Tests verify gRPC communication failure handling
    - Expected behavior: Traffic continues unaffected when gRPC server is down
    - Mux mode config commands should work even when gRPC server is stopped
    - State DB checks are skipped (skip_state_db=True) when gRPC is down
    - Standby ToR health shows 'unhealthy' when gRPC is down
    - Zero disruption expected for all traffic tests during gRPC failure
    - gRPC server stop simulates SmartNIC communication loss
    - Tests verify graceful degradation: control plane may degrade but data plane continues

=============================================================================
"""

import pytest

from tests.common.dualtor.control_plane_utils import verify_tor_states
from tests.common.dualtor.data_plane_utils import send_t1_to_server_with_action     # noqa: F401
from tests.common.dualtor.data_plane_utils import send_server_to_t1_with_action     # noqa: F401
from tests.common.dualtor.dual_tor_utils import upper_tor_host                      # noqa: F401
from tests.common.dualtor.dual_tor_utils import lower_tor_host                      # noqa: F401
from tests.common.fixtures.ptfhost_utils import run_icmp_responder                  # noqa: F401
from tests.common.fixtures.ptfhost_utils import run_garp_service                    # noqa: F401
from tests.common.fixtures.ptfhost_utils import change_mac_addresses                # noqa: F401
from tests.common.dualtor.dual_tor_common import active_active_ports                # noqa: F401
from tests.common.dualtor.dual_tor_common import cable_type                         # noqa: F401
from tests.common.dualtor.dual_tor_common import CableType
from tests.common.dualtor.nic_simulator_control import stop_nic_grpc_server         # noqa: F401
from tests.common.dualtor.nic_simulator_control import restart_nic_simulator        # noqa: F401


pytestmark = [
    pytest.mark.topology("dualtor")
]


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_grpc_server_failure_config_standby_config_auto_upstream_active(
    upper_tor_host, lower_tor_host, send_server_to_t1_with_action,      # noqa: F811
    cable_type, active_active_ports, stop_nic_grpc_server               # noqa: F811
):
    if cable_type == CableType.active_active:
        stop_nic_grpc_server(active_active_ports)
        upper_tor_host.shell_cmds(cmds=["config mux mode standby %s" % _ for _ in active_active_ports])

        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health='unhealthy',
            cable_type=cable_type,
            skip_state_db=True,
        )

        send_server_to_t1_with_action(
            upper_tor_host,
            verify=True,
            allowed_disruption=0,
            action=lambda: upper_tor_host.shell("config mux mode auto all")
        )

        verify_tor_states(
            expected_active_host=[upper_tor_host, lower_tor_host],
            expected_standby_host=None,
            cable_type=cable_type,
            skip_state_db=True
        )


@pytest.mark.enable_active_active
@pytest.mark.skip_active_standby
def test_grpc_server_failure_config_standby_config_auto_downstream_standby(
    upper_tor_host, lower_tor_host, send_t1_to_server_with_action,      # noqa: F811
    cable_type, active_active_ports, stop_nic_grpc_server               # noqa: F811
):
    if cable_type == CableType.active_active:
        stop_nic_grpc_server(active_active_ports)
        upper_tor_host.shell_cmds(cmds=["config mux mode standby %s" % _ for _ in active_active_ports])

        verify_tor_states(
            expected_active_host=lower_tor_host,
            expected_standby_host=upper_tor_host,
            expected_standby_health='unhealthy',
            cable_type=cable_type,
            skip_state_db=True,
        )

        send_t1_to_server_with_action(
            upper_tor_host,
            verify=True,
            allowed_disruption=0,
            action=lambda: upper_tor_host.shell("config mux mode auto all")
        )

        verify_tor_states(
            expected_active_host=[upper_tor_host, lower_tor_host],
            expected_standby_host=None,
            cable_type=cable_type,
            skip_state_db=True
        )
