"""
=============================================================================
Module: log_fidelity
File: test_bgp_shutdown.py
=============================================================================

Description:
    This test validates log fidelity for BGP administrative state changes.
    It ensures that when BGP is administratively shut down, the expected log
    message appears in syslog, verifying proper logging of BGP state transitions.

Test Intent:
    - test_bgp_shutdown: Validates that shutting down all BGP sessions using
      'config bgp shutdown all' command produces the expected syslog message
      "admin state is set to 'down'". This ensures BGP administrative actions
      are properly logged for operational visibility and troubleshooting.
      Test restores BGP to operational state after verification.

Topology:
    any topology

Fixtures Used:
    - ignore_expected_loganalyzer_exception: Automatically ignores expected
      syncd errors related to SAI_API_TUNNEL MPTNL route event operations
      that can occur on dualtor topologies during BGP state changes
    - duthosts: Provides list of DUT hosts for testing
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one random frontend
      DUT per hardware SKU for testing
    - loganalyzer: Log analyzer fixture for monitoring system logs

Dependencies:
    - tests.common.plugins.loganalyzer.loganalyzer: Provides LogAnalyzer for
      syslog validation and LogAnalyzerError for error handling

Notes:
    - Test originally designed to run on linecards only
    - Uses LogAnalyzer to validate expected log message appears in syslog
    - BGP is restored to operational state in finally block to ensure cleanup
    - Ignores specific syncd tunnel-related errors that may occur on dualtor
      topologies: _brcm_sai_mptnl_tnl_route_event_add and
      _brcm_sai_mptnl_process_route_add_mode_default_and_host errors
    - Expected log message: "admin state is set to 'down'"
    - Commands used: 'config bgp shutdown all' and 'config bgp startup all'
=============================================================================
"""
import logging
import pytest

from tests.common.plugins.loganalyzer.loganalyzer import LogAnalyzer, LogAnalyzerError

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]


@pytest.fixture(autouse=True)
def ignore_expected_loganalyzer_exception(loganalyzer, duthosts):

    ignore_errors = [
        r".* ERR syncd#syncd: .*SAI_API_TUNNEL:_brcm_sai_mptnl_tnl_route_event_add:\d+ ecmp table entry lookup "
        "failed with error.*",
        r".* ERR syncd#syncd: .*SAI_API_TUNNEL:_brcm_sai_mptnl_process_route_add_mode_default_and_host:\d+ "
        "_brcm_sai_mptnl_tnl_route_event_add failed with error.*"
    ]

    if loganalyzer:
        for duthost in duthosts:
            loganalyzer[duthost.hostname].ignore_regex.extend(ignore_errors)

    return None


def check_syslog(duthost, prefix, trigger_action, expected_log, restore_action):
    loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix=prefix)
    loganalyzer.expect_regex = [expected_log]

    try:
        marker = loganalyzer.init()
        duthost.command(trigger_action)
        logger.info("Check for expected log {} in syslog".format(expected_log))
        loganalyzer.analyze(marker)

    except LogAnalyzerError as err:
        logger.error("Unable to find expected log in syslog")
        raise err

    finally:
        duthost.command(restore_action)


def test_bgp_shutdown(duthosts, enum_rand_one_per_hwsku_frontend_hostname):
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]

    BGP_DOWN_EXPECTED_LOG_MESSAGE = "admin state is set to 'down'"
    BGP_DOWN_COMMAND = "config bgp shutdown all"
    BGP_UP_COMMAND = "config bgp startup all"

    check_syslog(duthost, "bgp_shutdown", BGP_DOWN_COMMAND, BGP_DOWN_EXPECTED_LOG_MESSAGE, BGP_UP_COMMAND)
