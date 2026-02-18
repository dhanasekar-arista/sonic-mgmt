"""
=============================================================================
Module: syslog
File: test_syslog.py
=============================================================================

Description:
    This test file validates syslog message forwarding functionality on SONiC devices
    by configuring dummy syslog servers and verifying that syslog messages are properly
    sent to remote servers. It tests various combinations of IPv4 and IPv6 syslog
    servers, including single and dual server configurations, to ensure proper
    routing and delivery of syslog messages.

Test Intent:
    - test_syslog: Validates syslog message forwarding to remote servers by testing
      five different server configuration scenarios - (1) single IPv4 server,
      (2) single IPv6 server, (3) two IPv4 servers, (4) mixed IPv4 and IPv6 servers,
      and (5) two IPv6 servers. For each scenario, the test configures the syslog
      servers, triggers syslog messages on the DUT, captures packets on the server,
      and verifies that syslog messages are successfully received with correct
      formatting and content.

Topology:
    any (works with any topology type)

Fixtures Used:
    - rand_selected_dut: Randomly selects one DUT for testing
    - check_default_route: Validates that the DUT has a default route configured
      before attempting to send syslog messages to remote servers, ensuring
      network reachability

Dependencies:
    - pytest: Test framework
    - tests.common.helpers.syslog_helpers: Provides run_syslog and check_default_route
      functions for syslog testing logic

Notes:
    - Tests are marked for 'any' topology
    - Parametrized to test 5 different syslog server configurations
    - Supports both IPv4 (e.g., 7.0.80.166) and IPv6 (e.g., fd82:b34f:cc99::100) servers
    - Can configure up to 2 syslog servers simultaneously
    - Requires default route to be present for remote syslog forwarding
    - IPv6 syslog tests may be skipped on older SONiC versions (201911)
    - Uses pcap file capture for verifying syslog message receipt
    - Actual test logic is implemented in the run_syslog helper function
=============================================================================
"""
import logging
import pytest
from tests.common.helpers.syslog_helpers import run_syslog, check_default_route   # noqa F401

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology("any")
]


@pytest.mark.parametrize("dummy_syslog_server_ip_a, dummy_syslog_server_ip_b",
                         [("7.0.80.166", None),
                          ("fd82:b34f:cc99::100", None),
                          ("7.0.80.165", "7.0.80.166"),
                          ("fd82:b34f:cc99::100", "7.0.80.166"),
                          ("fd82:b34f:cc99::100", "fd82:b34f:cc99::200")])
def test_syslog(rand_selected_dut, dummy_syslog_server_ip_a, dummy_syslog_server_ip_b,
                check_default_route      # noqa: F811
                ):
    run_syslog(rand_selected_dut, dummy_syslog_server_ip_a, dummy_syslog_server_ip_b, check_default_route)
