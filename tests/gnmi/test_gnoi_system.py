"""
=============================================================================
Module: gnmi
File: test_gnoi_system.py
=============================================================================

Description:
    Tests gNOI (gRPC Network Operations Interface) System API. Validates
    system time retrieval via gNOI protocol.

Test Intent:
    - test_gnoi_system_time: Verifies System.Time API returns current system
      time in valid JSON format with nanosecond precision

Topology:
    Supports any topology

Fixtures Used:
    - duthosts: DUT host objects
    - rand_one_dut_hostname: Randomly selected DUT
    - localhost: Localhost for gNOI client operations

Dependencies:
    - .helper: gnoi_request for gNOI operations
    - tests.common.helpers.assertions: pytest_assert

Notes:
    - Response format: {"time":1735921221909617549} (nanoseconds since epoch)
    - Extracts first JSON substring from response
    - Validates time field presence in response
=============================================================================
"""

"""
Simple integration tests for gNOI System service.

All tests automatically run with TLS server configuration by default.
Users don't need to worry about TLS configuration.
"""
import pytest
import logging

from tests.common.fixtures.grpc_fixtures import gnmi_tls  # noqa: F401

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
]


def test_system_time(gnmi_tls):  # noqa: F811
    """Test System.Time RPC with TLS enabled by default."""
    result = gnmi_tls.gnoi.system_time()
    assert "time" in result
    assert isinstance(result["time"], int)
    logger.info(f"System time: {result['time']} nanoseconds since epoch")
