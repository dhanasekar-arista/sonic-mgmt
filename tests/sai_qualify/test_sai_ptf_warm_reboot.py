"""
=============================================================================
Module: sai_qualify
File: test_sai_ptf_warm_reboot.py
=============================================================================

Description:
    This test module runs SAI qualification tests using PTF framework during
    warm reboot scenarios. It validates SAI implementation behavior and data
    plane functionality during hitless upgrades by executing warm reboot test
    cases and ensuring proper recovery and state preservation across reboot.

Test Intent:
    - test_sai: Executes parametrized SAI test cases from WARM_REBOOT_PTF_TEST_CASE
      suite during warm reboot, validates data plane continuity, SAI state
      preservation, and proper warm reboot recovery, then stores results and
      performs cleanup operations

Topology:
    - Supported: ptf topology
    - Requires saiserver with warmboot support on DUT
    - PTF-based test execution against SAI layer

Fixtures Used:
    - sai_testbed: SAI test environment preparation
    - sai_test_env_check: Environment readiness validation
    - creds: Docker registry credentials
    - duthost: DUT host object
    - localhost: Local orchestration host
    - ptfhost: PTF server for test execution
    - request: Pytest request metadata
    - create_sai_test_interface_param: Interface configuration for testing
    - start_warm_reboot_watcher: Warm reboot monitoring fixture

Dependencies:
    - cases_ptf_warmreboot: PTF warm reboot test case definitions
    - sai_infra: SAI testing infrastructure and utilities
    - conftest: Shared configuration and fixtures

Notes:
    - Sanity checks disabled during warm reboot testing
    - Loganalyzer disabled for expected warm reboot log messages
    - DUT health checks skipped during reboot operations
    - SAI test container lifecycle managed per test case
    - Warmboot configuration restored after test completion
    - Test results archived on PTF host for post-analysis
    - Compatible with --sai_test_keep_test_env option for debugging
=============================================================================
"""

import pytest
import logging

from .cases_ptf_warmreboot import WARM_REBOOT_PTF_TEST_CASE
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


@pytest.mark.parametrize("ptf_sai_test_case", WARM_REBOOT_PTF_TEST_CASE)
def test_sai(
            sai_testbed,
            sai_test_env_check,
            creds,
            duthost,
            localhost,
            ptfhost,
            ptf_sai_test_case,
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
        run_case_from_ptf(duthost, dut_ip, ptfhost, ptf_sai_test_case, sai_test_interface_para, request)
    except BaseException as e:
        logger.info("Test case [{}] failed, failed as {}.".format(ptf_sai_test_case, e))
        pytest.fail("Test case [{}] failed".format(ptf_sai_test_case), e)
    finally:
        stop_and_rm_sai_test_container(
            duthost, get_sai_test_container_name(request))
        store_test_result(ptfhost)
        saiserver_warmboot_config(duthost, "restore")
        saiserver_warmboot_config(duthost, "init")
