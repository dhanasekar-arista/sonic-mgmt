"""
=============================================================================
Module: snappi_tests.dash
File: test_plannedswitchover.py
=============================================================================

Description:
    DASH High Availability (HA) Planned Switchover test suite for SmartSwitch dual-DUT
    topology using Snappi/IxLoad traffic generator. This module validates controlled
    DPU role transitions (active to standby, standby to active) during maintenance
    windows, ensuring graceful connection migration with minimal traffic disruption
    and zero connection loss during orchestrated switchover operations.

Test Intent:
    - test_ha_planned_switchover: Validates SmartSwitch graceful switchover behavior
      during planned maintenance. Tests controlled DPU role exchange with active
      traffic load, measuring connection migration time, dropped connections, and
      new connection establishment rate on newly-active DPU. Ensures hitless or
      near-hitless switchover with layer 7 HTTP traffic continuity.

Topology:
    - tgen: Traffic generator topology with IxLoad/Snappi L47 capabilities
    - Requires dual SmartSwitch DUTs with active-standby DPU configuration
    - Requires UHD (Universal Hardware Dataplane) with switchover API support
    - Traffic flows: Client -> Active DPU -> Server (before switchover)
                     Client -> Standby DPU (now active) -> Server (after switchover)

Fixtures Used:
    - duthosts: Collection of DUT host objects (2 SmartSwitches required)
    - localhost: Ansible localhost for orchestration and configuration
    - tbinfo: Testbed information including DPU IPs, MACs, interfaces, UHD IP/API
    - request: Pytest request object for dynamic fixture loading
    - ha_test_case: Parameterized test case name ('planned_switchover')
    - setup_config_snappi_l47: IxLoad layer 7 traffic configuration setup function
    - setup_config_npu_dpu: NPU-DPU static routes, ARPs, and DPU interface setup
    - setup_config_uhd_connect: UHD connectivity with switchover API configuration
    - config_snappi_l47: Resolved IxLoad L47 configuration
    - config_npu_dpu: Resolved NPU-DPU configuration

Dependencies:
    - tests.snappi_tests.dash.ha.ha_helper: HA test orchestration (run_planned_switchover)
    - tests.common.snappi_tests.snappi_fixtures: Snappi/UHD configuration utilities
    - tests.common.snappi_tests.ixload.snappi_fixtures: IxLoad L47 fixtures
    - concurrent.futures: Parallel fixture execution for faster test setup
    - snappi: Snappi API for traffic configuration and metrics collection
    - requests: HTTP/HTTPS client for UHD switchover API (POST /api/v1/control/operations/switchover)
    - ipaddress, macaddress: Network address manipulation utilities

Notes:
    - Test requires exactly 2 SmartSwitch DUTs (both checked for SmartSwitch subtype)
    - Test skipped if either DUT is not a SmartSwitch
    - Parallel setup functions execute concurrently (3 workers) for efficiency
    - Switchover triggered via UHD API: POST https://<uhd_ip>/connect/api/v1/control/operations/switchover
    - Switchover payload: {"enable": true} to trigger, {"enable": false} to stop
    - UHD handles traffic redirection between DPUs during switchover
    - Static routes and ARP entries configured for both DPU IPs (active/standby)
    - Testbed requires: dpu_active_ip/mac/if, dpu_standby_ip/mac/if, uhd_ip
    - Log analyzer disabled to prevent false positives during switchover
    - Test measures: switchover time, connection drops, CPS during transition
    - Graceful drain: active DPU stops accepting new connections before handoff
    - Git history: Added/updated in d88ea648c (testcases 2 and 3), a4b318516 (testcase 1)
    - Related test cases: test_cps, test_dpuloss

=============================================================================
"""

from tests.common.helpers.assertions import pytest_assert, pytest_require  # noqa F401
from tests.snappi_tests.dash.ha.ha_helper import is_smartswitch, run_ha_test
from tests.common.snappi_tests.snappi_fixtures import config_uhd_connect  # noqa F401
from tests.common.snappi_tests.ixload.snappi_fixtures import config_snappi_l47  # noqa F401
from tests.common.snappi_tests.ixload.snappi_fixtures import config_npu_dpu  # noqa F401
from tests.common.snappi_tests.ixload.snappi_fixtures import setup_config_snappi_l47, setup_config_npu_dpu  # noqa F401
from tests.common.snappi_tests.snappi_fixtures import setup_config_uhd_connect  # noqa F401
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
import snappi  # noqa F401
import requests  # noqa F401
import json  # noqa F401
import ipaddress
import macaddress

SNAPPI_POLL_DELAY_SEC = 2

ipp = ipaddress.ip_address
maca = macaddress.MAC


pytestmark = [pytest.mark.topology('tgen')]


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize('ha_test_case', ['planned_switchover'])
def test_ha_planned_switchover(
                       duthosts,
                       localhost,
                       tbinfo,
                       ha_test_case,
                       request,
): # noqa F811

    results = {}
    errors = {}

    sw1 = is_smartswitch(duthosts[0])
    if sw1 is False:
        pytest.skip("Skipping test since is not a smartswitch")
    sw2 = is_smartswitch(duthosts[1])
    if sw2 is False:
        pytest.skip("Skipping test since DUT is not a smartswitch")

    def _run_config_snappi_l47():
        try:
            return setup_config_snappi_l47(request, duthosts, tbinfo, ha_test_case)
        except Exception as e:
            raise e

    def _run_config_npu_dpu():
        try:
            return setup_config_npu_dpu(request, duthosts, localhost, tbinfo, ha_test_case)
        except Exception as e:
            raise e

    def _run_config_uhd_connect():
        try:
            return setup_config_uhd_connect(request, tbinfo, ha_test_case)
        except Exception as e:
            raise e

    # Run the setup functions in parallel
    with ThreadPoolExecutor(max_workers=3) as ex:
        future_snappi = ex.submit(_run_config_snappi_l47)
        future_npu = ex.submit(_run_config_npu_dpu)
        future_uhd = ex.submit(_run_config_uhd_connect)

        futures = {
            future_snappi: "config_snappi_l47",
            future_npu: "config_npu_dpu",
            future_uhd: "config_uhd_connect"
        }

        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as e:
                errors[name] = e

    pytest_require(not errors, f"Concurrent setup failed for: {errors}")
    pytest_require("config_snappi_l47" in results, "Missing config_snappi_l47 result")
    pytest_require("config_npu_dpu" in results, "Missing config_npu_dpu result")

    config_npu_dpu = results["config_npu_dpu"]  # noqa F811
    config_snappi_l47 = results["config_snappi_l47"]  # noqa F811

    run_ha_test(  # noqa F405
                duthosts,
                localhost,
                tbinfo,
                ha_test_case,
                config_npu_dpu,
                config_snappi_l47,)

    return
