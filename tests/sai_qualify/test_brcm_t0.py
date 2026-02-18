"""
=============================================================================
Module: sai_qualify
File: test_brcm_t0.py
=============================================================================

Description:
    This test module runs SAI qualification tests specifically designed for
    Broadcom chipsets in T0 topology. It validates Broadcom-specific SAI
    implementation features, data plane behavior, and ASIC-specific functionality
    using PTF framework test cases tailored for Broadcom hardware.

Test Intent:
    - test_sai: Executes parametrized Broadcom T0 SAI test cases from TEST_CASE
      suite, validates Broadcom ASIC-specific SAI behavior, data plane packet
      processing, and proper integration with Broadcom SDK, then stores results
      and cleans up test containers

Topology:
    - Supported: ptf topology
    - Target: Broadcom chipsets in T0 configuration
    - Requires saiserver with Broadcom SAI implementation

Fixtures Used:
    - sai_testbed: SAI test environment setup
    - sai_test_env_check: Environment validation fixture
    - creds: Docker registry credentials
    - duthost: DUT host object (must have Broadcom ASIC)
    - ptfhost: PTF server for test execution
    - request: Pytest request metadata
    - create_sai_test_interface_param: Interface parameters for SAI testing

Dependencies:
    - cases_brcm_t0: Broadcom T0-specific SAI test case definitions
    - sai_infra: SAI test infrastructure and execution framework
    - conftest: Shared fixtures and configuration

Notes:
    - Tests are Broadcom chipset-specific (not vendor-agnostic)
    - Sanity checks skipped for SAI-level testing
    - Loganalyzer disabled during SAI test execution
    - DUT health checks disabled for SAI testing focus
    - SAI test container cleaned up after each test case
    - Test results stored on PTF host for analysis
    - Test failures trigger container cleanup before reporting
    - Compatible with Broadcom SDK SAI implementation
=============================================================================
"""

import pytest
import logging

from .cases_brcm_t0 import TEST_CASE
from .conftest import get_sai_test_container_name
from .conftest import stop_and_rm_sai_test_container
from .sai_infra import run_case_from_ptf, store_test_result
from .sai_infra import *  # noqa: F403,F401
from .conftest import *  # noqa: F403,F401

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology("ptf"),
    pytest.mark.sanity_check(skip_sanity=True),
    pytest.mark.disable_loganalyzer,
    pytest.mark.skip_check_dut_health
]


@pytest.mark.parametrize("sai_test_case", TEST_CASE)
def test_sai(sai_testbed,
             sai_test_env_check,
             creds,
             duthost,
             ptfhost,
             sai_test_case,
             request,
             create_sai_test_interface_param):
    """
    Trigger brcm t0 test here.

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
    dut_ip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']
    try:
        sai_test_interface_para = create_sai_test_interface_param
        run_case_from_ptf(
            duthost, dut_ip, ptfhost,
            sai_test_case, sai_test_interface_para, request)
    except BaseException as e:
        logger.info("Test case [{}] failed, \
            trying to restart sai test container, \
                failed as {}.".format(sai_test_case, e))
        pytest.fail("Test case [{}] failed".format(sai_test_case), e)
    finally:
        stop_and_rm_sai_test_container(
            duthost, get_sai_test_container_name(request))
        store_test_result(ptfhost)
