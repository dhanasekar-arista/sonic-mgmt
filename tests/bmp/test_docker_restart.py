"""
=============================================================================
Module: bmp
File: test_docker_restart.py
=============================================================================

Description:
    This module tests BMP docker container restart functionality and validates
    that the BMP service can be cleanly restarted and that all critical system
    services return to a fully operational state. It ensures proper container
    lifecycle management and service recovery.

Test Intent:
    - test_restart_bmp_docker: Validates that BMP docker container can be
      restarted without causing system instability. Verifies that after
      restart, all critical services (including BMP itself) reach fully
      started state within expected timeout, ensuring proper service recovery
      and system stability on both single-asic and multi-asic platforms.

Topology:
    any - Works with any topology

Fixtures Used:
    - duthosts: Multi-DUT fixture providing access to all DUTs in the testbed
    - enum_rand_one_per_hwsku_frontend_hostname: Randomly selects one frontend
      DUT per hardware SKU to ensure diverse testing coverage
    - enum_rand_one_frontend_asic_index: Randomly selects one ASIC index on
      frontend for multi-asic platforms

Dependencies:
    - tests.common.utilities: Common utilities including wait_until for polling
    - tests.common.helpers.assertions: Assertion helpers for pytest validation
    - bmp docker container: BMP service container
    - asic_instance: Multi-asic support for service management

Notes:
    - Test waits up to 300 seconds with 20 second intervals for full recovery
    - Validates critical_services_fully_started() after restart
    - Logs docker ps output before and after restart for debugging
    - Fixed for multi-asic support to properly handle ASIC-specific service restart
    - Ensures clean shutdown and startup of BMP container and associated services
=============================================================================
"""
import pytest
import logging

from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]


def test_restart_bmp_docker(duthosts,
                            enum_rand_one_per_hwsku_frontend_hostname,
                            enum_rand_one_frontend_asic_index):
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    asichost = duthost.asic_instance(enum_rand_one_frontend_asic_index)

    logger.info(duthost.shell(cmd="docker ps", module_ignore_errors=True)['stdout'])
    asichost.restart_service("bmp")
    logger.info(duthost.shell(cmd="docker ps", module_ignore_errors=True)['stdout'])

    logger.info("Wait until the system is stable")
    pytest_assert(wait_until(300, 20, 0, duthost.critical_services_fully_started),
                  "Not all critical services are fully started")
