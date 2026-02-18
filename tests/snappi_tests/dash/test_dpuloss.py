"""
=============================================================================
Module: snappi_tests.dash
File: test_dpuloss.py
=============================================================================

Description:
    DASH High Availability (HA) DPU Loss test suite for SmartSwitch dual-DUT topology
    using Snappi/IxLoad traffic generator. This module validates SmartSwitch resilience
    and traffic continuity when one DPU fails or is removed from service, ensuring
    seamless failover to the standby DPU while maintaining active layer 7 connections.

Test Intent:
    - test_ha_dpuloss: Validates SmartSwitch HA behavior during DPU failure scenarios.
      Tests traffic continuity, connection migration, and performance degradation
      during active DPU loss. Ensures standby DPU can handle production traffic load
      with acceptable connection establishment rates and minimal connection drops.

Topology:
    - tgen: Traffic generator topology with IxLoad/Snappi L47 capabilities
    - Requires dual SmartSwitch DUTs with active-standby DPU configuration
    - Requires UHD (Universal Hardware Dataplane) connectivity for traffic switching

Fixtures Used:
    - duthosts: Collection of DUT host objects (2 SmartSwitches required)
    - localhost: Ansible localhost for orchestration and configuration
    - tbinfo: Testbed information including DPU IPs, MACs, interfaces, and UHD settings
    - request: Pytest request object for dynamic fixture loading
    - ha_test_case: Parameterized test case name ('dpuloss')
    - setup_config_snappi_l47: IxLoad layer 7 traffic configuration setup function
    - setup_config_npu_dpu: NPU-DPU static routes, ARPs, and DPU interface setup
    - setup_config_uhd_connect: UHD connectivity configuration for traffic redirection
    - config_snappi_l47: Resolved IxLoad L47 configuration
    - config_npu_dpu: Resolved NPU-DPU configuration

Dependencies:
    - tests.snappi_tests.dash.ha.ha_helper: HA test orchestration (run_dpuloss)
    - tests.common.snappi_tests.snappi_fixtures: Snappi/UHD configuration utilities
    - tests.common.snappi_tests.ixload.snappi_fixtures: IxLoad L47 fixtures
    - concurrent.futures: Parallel fixture execution for faster test setup
    - snappi: Snappi API for traffic configuration and control
    - requests: HTTP client for UHD API communication
    - ipaddress, macaddress: Network address manipulation utilities

Notes:
    - Test requires exactly 2 SmartSwitch DUTs (both checked for SmartSwitch subtype)
    - Test skipped if either DUT is not a SmartSwitch
    - Parallel setup functions execute concurrently (3 workers) for efficiency
    - DPU loss simulated by: interface shutdown, process kill, or physical disconnect
    - UHD controls traffic switchover between active and standby DPUs
    - Static routes and ARP entries configured for both DPU loopback and interface IPs
    - DPU active/standby configuration: dpu_active_ip, dpu_standby_ip from tbinfo
    - Log analyzer disabled to prevent false positives during DPU failure
    - Test measures: connection drop count, failover time, new CPS on standby DPU
    - Git history: Added in b8e501afc (HA Smartswitch testcase 12 DPU Loss)
    - Related test cases: test_cps, test_planned_switchover

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
@pytest.mark.parametrize('ha_test_case', ['dpuloss'])
def test_ha_dpuloss(
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
