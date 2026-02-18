"""
=============================================================================
Module: sai_qualify
File: test_sai_t0_warm_reboot.py
=============================================================================

Description:
    This test module runs SAI (Switch Abstraction Interface) qualification tests
    for T0 topology during warm reboot scenarios. It validates that SAI test cases
    execute correctly while the switch undergoes warm reboot, ensuring data plane
    continuity and proper SAI implementation behavior during hitless upgrades.

Test Intent:
    - test_sai: Executes parametrized SAI test cases from WARM_REBOOT_T0_TEST_CASE
      suite on a T0 topology during warm reboot, validates SAI behavior and data
      plane forwarding, stores test results, and ensures proper cleanup of test
      containers and warmboot configuration restoration

Topology:
    - Supported: ptf topology
    - Requires saiserver running on DUT with warmboot configuration
    - Tests executed via PTF framework against SAI implementation

Fixtures Used:
    - sai_testbed: Prepares SAI test environment and testbed setup
    - sai_test_env_check: Validates test environment readiness
    - creds: Docker registry credentials for container access
    - duthost: DUT host object for switch under test
    - localhost: Local host for test orchestration
    - ptfhost: PTF server for running SAI test cases
    - request: Pytest request object for test metadata
    - create_sai_test_interface_param: Interface parameters for SAI testing
    - start_warm_reboot_watcher: Monitors warm reboot process during test

Dependencies:
    - cases_t0_warmreboot: Test case definitions for T0 warm reboot scenarios
    - sai_infra: SAI test infrastructure for running PTF-based tests
    - conftest: Shared fixtures and helper functions

Notes:
    - Sanity checks are skipped (mark: skip_sanity=True)
    - Loganalyzer is disabled due to expected reboot-related log messages
    - DUT health checks are skipped during warm reboot testing
    - SAI test container is cleaned up after each test case
    - Warmboot configuration is restored to original state after testing
    - Test results are stored on PTF host for analysis
    - Test environment can be preserved with --sai_test_keep_test_env option
=============================================================================
"""

import pytest
import logging

from .cases_t0_warmreboot import WARM_REBOOT_T0_TEST_CASE
from .conftest import get_sai_test_container_name
from .conftest import saiserver_warmboot_config
from .conftest import stop_and_rm_sai_test_container
from .sai_infra import run_case_from_ptf
from .sai_infra import store_test_result
from .sai_infra import *  # noqa: F403 F401
from .conftest import *  # noqa: F403 F401


logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology("ptf"),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
    pytest.mark.skip_check_dut_health
]


@pytest.mark.parametrize("sai_test_case", WARM_REBOOT_T0_TEST_CASE)
def test_sai(
            sai_testbed,
            sai_test_env_check,
            creds,
            duthost,
            localhost,
            ptfhost,
            sai_test_case,
            request,
            create_sai_test_interface_param,
            start_warm_reboot_watcher):
    """
    Trigger warm reboot test here.

    Args:
        sai_testbed: Fixture which can help prepare the sai testbed.
        sai_test_env_check: Fixture, use to check the test env.
        creds (dict): Credentials used to access the docker registry.
        duthost (SonicHost): The target device.
        ptfhost (AnsibleHost): The PTF server.
        sai_test_case: Test case name used to make test.
        request: Pytest request.
        create_sai_test_interface_param: Testbed switch interface
    """
    logger.info("sai_test_keep_test_env {}".format(request.config.option.sai_test_keep_test_env))
    dut_ip = duthost.host.options['inventory_manager'].get_host(duthost.hostname).vars['ansible_host']
    try:
        sai_test_interface_para = create_sai_test_interface_param
        run_case_from_ptf(duthost, dut_ip, ptfhost, sai_test_case, sai_test_interface_para, request)
    except BaseException as e:
        logger.info("Test case [{}] failed, failed as {}.".format(sai_test_case, e))
        pytest.fail("Test case [{}] failed".format(sai_test_case), e)
    finally:
        stop_and_rm_sai_test_container(
            duthost, get_sai_test_container_name(request))
        store_test_result(ptfhost)
        saiserver_warmboot_config(duthost, "restore")
        saiserver_warmboot_config(duthost, "init")
