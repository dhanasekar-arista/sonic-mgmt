"""
=============================================================================
Module: snappi_tests.dash
File: test_cps.py
=============================================================================

Description:
    DASH High Availability (HA) Connections Per Second (CPS) test suite for SmartSwitch
    topology using Snappi/IxLoad traffic generator. This module validates the maximum
    sustainable CPS (connections per second) rate that a SmartSwitch DPU can handle
    while maintaining service availability through layer 7 HTTP traffic testing.

Test Intent:
    - test_cps_baby_hero: Validates SmartSwitch CPS capacity using binary search
      algorithm to find maximum sustainable connection rate. Tests DPU performance
      under layer 7 HTTP traffic load, measuring successful connection establishment
      and teardown rates across NPU-DPU dataplane.

Topology:
    - tgen: Traffic generator topology with IxLoad/Snappi L47 capabilities
    - Requires SmartSwitch with DPU-NPU architecture
    - Requires UHD (Universal Hardware Dataplane) connectivity

Fixtures Used:
    - duthost: Device Under Test (NPU) host object
    - localhost: Ansible localhost for orchestration
    - tbinfo: Testbed information including MAC addresses and IPs
    - request: Pytest request object for dynamic fixture loading
    - config_snappi_l47: IxLoad layer 7 traffic configuration fixture
    - config_npu_dpu: NPU-DPU static route and ARP configuration fixture
    - config_uhd_connect: UHD connectivity configuration fixture
    - ha_test_case: Parameterized test case name ('cps')

Dependencies:
    - tests.snappi_tests.dash.ha.ha_helper: HA test execution and SmartSwitch detection
    - tests.common.snappi_tests.snappi_fixtures: Snappi/UHD configuration utilities
    - tests.common.snappi_tests.ixload.snappi_fixtures: IxLoad L47 fixtures
    - concurrent.futures: Parallel fixture execution for faster test setup
    - snappi: Snappi API for traffic configuration
    - requests: HTTP client for API communication
    - ipaddress, macaddress: Network address manipulation utilities

Notes:
    - Test skipped if DUT is not a SmartSwitch (checks DEVICE_METADATA subtype)
    - Parallel fixture loading used to reduce test setup time (3 workers)
    - CPS search performed via run_cps_search() in ha_helper
    - Binary search algorithm determines maximum sustainable CPS
    - Log analyzer disabled to prevent false positives during traffic stress
    - Test validates L7 HTTP connection lifecycle (TCP + HTTP GET/POST)
    - Requires testbed with l47_tg_clientmac, l47_tg_servermac, dut_mac configured
    - Git history: Added in a4b318516, updated in d88ea648c
    - Related test cases: test_dpuloss, test_planned_switchover

=============================================================================
"""

from tests.common.helpers.assertions import pytest_assert, pytest_require  # noqa F401
from tests.snappi_tests.dash.ha.ha_helper import is_smartswitch, run_ha_test
from tests.common.snappi_tests.snappi_fixtures import config_uhd_connect  # noqa F401
from tests.common.snappi_tests.ixload.snappi_fixtures import config_snappi_l47  # noqa F401
from tests.common.snappi_tests.ixload.snappi_fixtures import config_npu_dpu  # noqa F401
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
@pytest.mark.parametrize('ha_test_case', ['cps'])
def test_cps_baby_hero(
                       duthost,
                       localhost,
                       tbinfo,
                       ha_test_case,
                       request,
): # noqa F811

    fixture_names = ["config_snappi_l47", "config_npu_dpu", "config_uhd_connect"]

    results = {}
    errors = {}

    sw1 = is_smartswitch(duthost)
    if sw1 is False:
        pytest.skip("Skipping test since is not a smartswitch")

    def _resolve_fixture(name):
        # Resolve the fixture value on-demand
        return request.getfixturevalue(name)

    with ThreadPoolExecutor(max_workers=3) as ex:
        fm = {ex.submit(_resolve_fixture, name): name for name in fixture_names}
        for fut in as_completed(fm):
            name = fm[fut]
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
                duthost,
                localhost,
                tbinfo,
                ha_test_case,
                config_npu_dpu,
                config_snappi_l47,)

    return
