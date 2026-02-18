"""
=============================================================================
Module: sai_qualify
File: test_community.py
=============================================================================

Description:
    This test module runs SAI community test cases to validate SAI implementation
    using community-contributed test suites. It includes enhanced environment
    checking with liveness probes and automatic test environment reset capabilities
    to ensure test reliability. The module validates SAI behavior using community-
    standard test cases with built-in resilience mechanisms.

Test Intent:
    - test_sai: Executes parametrized community SAI test cases with advanced
      environment validation, including liveness checks and automatic environment
      reset on failures, validates SAI API correctness and data plane behavior,
      and stores test results for analysis

Topology:
    - Supported: ptf topology
    - Requires saiserver with community test support
    - PTF framework for test execution

Fixtures Used:
    - sai_testbed: SAI test environment preparation
    - sai_community_test_env_check: Community-specific environment validation with
      liveness checks and automatic reset capabilities
    - creds: Docker registry credentials
    - duthost: DUT host object
    - ptfhost: PTF server for test execution
    - request: Pytest request metadata
    - create_sai_test_interface_param: Interface configuration for testing

Dependencies:
    - cases_community: Community SAI test case definitions and probe tests
    - sai_infra: SAI infrastructure with liveness checking and reset utilities
    - conftest: Shared configuration and fixtures

Notes:
    - Environment check includes three-stage validation process:
      1. Liveness check using PROBE_TEST_CASE
      2. Automatic environment reset on liveness check failure
      3. Environment marked as failed after max reset attempts
    - Liveness check interval: LIVENESS_CHECK_INTERVAL_IN_SEC
    - Maximum reset attempts: SAI_TEST_ENV_RESET_TIMES
    - SAI test container cleaned up only on test failure
    - Test results stored on PTF host after execution
    - Sanity checks and health checks disabled for community testing
    - Loganalyzer disabled for SAI-specific validation
=============================================================================
"""

import time
import pytest
import logging

from .cases_community import PROBE_TEST_CASE, TEST_CASE
from .conftest import get_sai_test_container_name
from .sai_infra import LIVENESS_CHECK_INTERVAL_IN_SEC
from .conftest import stop_and_rm_sai_test_container
from .sai_infra import SAI_TEST_ENV_RESET_TIMES
from .sai_infra import reset_sai_test_dut
from .sai_infra import run_case_from_ptf
from .sai_infra import sai_test_container_liveness_check
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


@pytest.mark.parametrize("community_test_case", TEST_CASE)
def test_sai(sai_testbed, sai_community_test_env_check,
             creds, duthost, ptfhost,
             community_test_case, request, create_sai_test_interface_param):
    """
    Trigger the community test here.

    Args:
        sai_testbed: Fixture which can help prepare the sai testbed.
        sai_community_test_env_check: Fixture, use to check the test env.
        creds (dict): Credentials used to access the docker registry.
        duthost (SonicHost): The target device.
        ptfhost (AnsibleHost): The PTF server.
        sai_test_case: Test case name used to make test.
        request: Pytest request.
        create_sai_test_interface_param: Testbed switch interface
    """
    dut_ip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']
    try:
        sai_test_interface_para = create_sai_test_interface_param
        run_case_from_ptf(
            duthost, dut_ip, ptfhost,
            community_test_case, sai_test_interface_para, request)
    except BaseException as e:
        logger.info("Test case [{}] failed, \
            trying to restart sai test container,\
                 failed as {}.".format(community_test_case, e))
        stop_and_rm_sai_test_container(
            duthost, get_sai_test_container_name(request))
        pytest.fail("Test case [{}] failed".format(community_test_case), e)
    finally:
        store_test_result(ptfhost)


@pytest.fixture
def sai_community_test_env_check(creds, duthost,
                                 ptfhost, request,
                                 create_sai_test_interface_param):
    """
    Check the sai test environment.
    In this function, it will make a liveness check test
    to check if the sai test container is ready for test.
    This check has three stage:
    1. If the liveness check test failed,
    then it will make a environment reset.
    2. If the envvironment reset failed with attempts,
    then the test environment will be marked as failed.
    3. If environment marked as failed,
    this check will be failed in following round of check.

    Args:
        creds (dict): Credentials used to access the docker registry.
        duthost (SonicHost): The target device.
        dut_ip: dut ip address.
        ptfhost (AnsibleHost): The PTF server.
        test_case: Test case name used to make test.
        test_interface_params: Testbed switch interface
        request: Pytest request.
    """
    global IS_TEST_ENV_FAILED
    if IS_TEST_ENV_FAILED:
        logger.info("Test env check is failed in previous check.\
             Fails this check directly.")
        raise Exception("SAI Test env error.")

    check_commun_test_env_with_retry(
        creds, duthost, ptfhost, request, create_sai_test_interface_param)


def check_commun_test_env_with_retry(creds, duthost,
                                     ptfhost, request,
                                     create_sai_test_interface_param):
    """
    Args:
        creds (dict): Credentials used to access the docker registry.
        duthost (SonicHost): The target device.
        ptfhost (AnsibleHost): The PTF server.
        request: Pytest request.
        create_sai_test_interface_param: Fixture to create the sai
         test interface parameter.
    """
    global IS_TEST_ENV_FAILED
    for retry in range(SAI_TEST_ENV_RESET_TIMES):
        try:
            sai_test_interface_para = create_sai_test_interface_param
            sai_test_container_liveness_check(
                duthost, ptfhost, PROBE_TEST_CASE,
                request, sai_test_interface_para)
            break
        except BaseException as e:
            logger.info("Run test env check failed, reset the env, \
                retry: [{}/{}], failed as \
                    {}.".format(retry + 1, SAI_TEST_ENV_RESET_TIMES, e))
            if retry + 1 < SAI_TEST_ENV_RESET_TIMES:
                reset_sai_test_dut(duthost, creds, request)
                logger.info("Liveness check waiting {} \
                    sec for another retry.".format(
                        LIVENESS_CHECK_INTERVAL_IN_SEC))
                time.sleep(LIVENESS_CHECK_INTERVAL_IN_SEC)
            else:
                logger.info("Run test env check failed. \
                    Run test env is not ready. Error: {}".format(e))
                IS_TEST_ENV_FAILED = True
                raise e
