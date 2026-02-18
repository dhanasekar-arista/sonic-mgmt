"""
Module: tests.database
File: test_db_config.py

Description:
    This module contains test cases for validating Redis database configuration in SONiC.
    It verifies critical Redis settings including persistence configuration, database count,
    and Unix socket configuration to ensure proper database operation and performance.

Test Intent:
    - Verify Redis persistence (save) is disabled to prevent automatic disk writes,
      ensuring database runs in memory-only mode for performance
    - Validate that Redis is configured to support exactly 100 databases as required
      by SONiC architecture
    - Confirm Redis Unix socket is properly configured at /var/run/redis/redis.sock
      for local inter-process communication

Topology:
    - any: Tests can run on any topology (t0, t1, t2, dualtor, multi-asic, etc.)

Fixtures Used:
    - duthosts: Session-scoped fixture providing DutHosts object containing all DUTs
      in the testbed (defined in tests/conftest.py)
    - rand_one_dut_hostname: Module-scoped fixture that randomly selects one DUT
      hostname from the testbed (defined in tests/conftest.py)

Dependencies:
    - tests.common.helpers.assertions.pytest_assert: Custom assertion helper for better
      error messages and test reporting
    - redis-cli: Redis command-line interface must be available on the DUT
    - Redis: Redis server must be running on the DUT
    - JSON: Standard library for parsing Redis JSON-formatted responses

Notes:
    - All tests use redis-cli with --json flag to get machine-readable output
    - Redis save configuration should be empty string ("") indicating no automatic
      persistence to disk, as SONiC manages database persistence separately
    - SONiC requires exactly 100 databases to support all database instances:
      * Database 0-9: Reserved for various SONiC applications
      * Remaining databases: Available for dynamic allocation
    - Unix socket at /var/run/redis/redis.sock enables local applications to
      communicate with Redis without TCP/IP overhead
    - These configuration checks are critical for ensuring proper SONiC database
      operation and performance characteristics
    - Tests apply to all device types (physical and virtual)

Git History:
    96846209b Add some tests to verify Redis DB configuration (#12877)
"""
import logging
import pytest
import json

from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]


def test_redis_save_disabled(duthosts, rand_one_dut_hostname):
    """
    @summary: Test that the database isn't being saved to disk
    """
    duthost = duthosts[rand_one_dut_hostname]

    save_config_json = duthost.command(argv=["redis-cli", "--json", "CONFIG", "GET", "save"])["stdout"]
    save_config = json.loads(save_config_json)
    pytest_assert(save_config["save"] == "", "Redis should not be persisting contents to disk, save config is {}"
                  .format(save_config["save"]))


def test_redis_database_count(duthosts, rand_one_dut_hostname):
    """
    @summary: Test that redis is configured to support 100 databases
    """
    duthost = duthosts[rand_one_dut_hostname]

    database_config_json = duthost.command(argv=["redis-cli", "--json", "CONFIG", "GET", "databases"])["stdout"]
    database_config = json.loads(database_config_json)
    pytest_assert(database_config["databases"] == "100", "Redis is configured to support {} instead of 100 databases"
                  .format(database_config["databases"]))


def test_redis_unix_socket(duthosts, rand_one_dut_hostname):
    """
    @summary: Test that redis has the unix socket option enabled
    """
    duthost = duthosts[rand_one_dut_hostname]

    unixsocket_config_json = duthost.command(argv=["redis-cli", "--json", "CONFIG", "GET", "unixsocket"])["stdout"]
    unixsocket_config = json.loads(unixsocket_config_json)
    pytest_assert(unixsocket_config["unixsocket"] == "/var/run/redis/redis.sock",
                  "Redis unixsocket is not configured correctly")
