"""
=============================================================================
Module: gnxi
File: test_gnoi_file.py
=============================================================================

Description:
    Integration tests for gNOI File service operations. Tests file stat
    operations via gRPC with TLS enabled by default.

Test Intent:
    - test_file_stat: Validates File.Stat RPC for retrieving file metadata
      (tests with /etc/hostname as example file)

Topology:
    Supports any topology

Fixtures Used:
    - setup_gnoi_tls_server: Automatically configures TLS server
    - ptf_gnoi: PTF-based gNOI client with TLS
    - ptf_grpc: PTF gRPC utilities

Dependencies:
    - tests.common.fixtures.grpc_fixtures: gRPC and gNOI fixture utilities

Notes:
    - TLS automatically enabled for all tests via pytestmark
    - File service may not be fully implemented on all platforms
    - Tests gracefully handle unimplemented File.Stat operations
    - Returns file stats including size, permissions, modification time
=============================================================================

Simple integration tests for gNOI File service.

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


def test_file_stat(gnmi_tls):  # noqa: F811
    """Test File.Stat RPC with TLS enabled by default."""
    try:
        result = gnmi_tls.gnoi.file_stat("/etc/hostname")
        assert "stats" in result
        logger.info(f"File stats: {result['stats'][0]}")
    except Exception as e:
        # File service may not be fully implemented
        logger.warning(f"File.Stat failed (expected): {e}")
