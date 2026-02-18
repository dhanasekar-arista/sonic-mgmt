"""
=============================================================================
Module: bmp
File: test_bmp_redis_instance.py
=============================================================================

Description:
    This module validates that the BMP-specific Redis database instance is
    properly running within the database container. It checks that redis_bmp
    process is managed by supervisord and in RUNNING state, ensuring the
    fundamental database infrastructure for BMP feature is operational.

Test Intent:
    - test_bmp_redis_instance: Verifies that redis_bmp instance is running
      under supervisord control within the database docker container. This
      validates the basic infrastructure requirement for BMP feature by
      confirming the dedicated Redis instance for BMP state storage is
      properly initialized and operational.

Topology:
    any - Works with any topology

Fixtures Used:
    - duthosts: Multi-DUT fixture providing access to all DUTs in the testbed
    - rand_one_dut_hostname: Randomly selects one DUT hostname from available DUTs

Dependencies:
    - database docker container: Main database container hosting Redis instances
    - supervisord: Process control system managing Redis instances
    - redis_bmp: Dedicated Redis instance for BMP feature (typically redis6)

Notes:
    - Test uses supervisorctl to check process status within database container
    - Validates both presence and RUNNING status of redis_bmp process
    - This is a foundational test ensuring BMP database infrastructure exists
    - Does not validate actual BMP data, only the database instance itself
=============================================================================
"""
import logging
import pytest

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]


def ps_check_bmp_redis(duthost):

    cmd_ps = 'docker exec database supervisorctl status'
    logging.debug("ps_check_bmp_redis command is: {}".format(cmd_ps))
    ret = duthost.command(cmd_ps, module_ignore_errors=True)
    logging.debug("ps_check_bmp_redis output is: {}".format(ret))
    return ret


def test_bmp_redis_instance(duthosts, rand_one_dut_hostname):
    """
    @summary: Test that redis has bmp instance
    """
    duthost = duthosts[rand_one_dut_hostname]
    output = ps_check_bmp_redis(duthost)
    stdout_lines = output['stdout'].split('\n')

    for line in stdout_lines:
        if 'redis_bmp' in line and 'RUNNING' in line:
            assert True, "redis_bmp is in RUNNING status"
            break
    else:
        assert False, "redis_bmp is not in RUNNING status"
