"""
=============================================================================
Module: telemetry
File: test_telemetry_show_cli.py
=============================================================================

Description:
    This test file validates gNMI integration with SONiC CLI SHOW commands,
    allowing network operators to retrieve show command output via gNMI protocol.
    It tests that various SHOW commands (reboot-cause, interfaces, bgp, etc.) can
    be accessed through gNMI GET operations and that non-GET operations are properly
    rejected for read-only SHOW targets.

Test Intent:
    - test_telemetry_show_non_get: Validates that SHOW target only supports GET
      method by attempting a SUBSCRIBE operation on reboot-cause path and verifying
      it fails with appropriate error, ensuring SHOW commands are read-only via gNMI.
    - test_telemetry_show_get: Tests gNMI GET operations for all SHOW command paths
      defined in cli_paths.json by executing required setup functions, querying
      each show command via gNMI GET, and verifying output format and content using
      validation functions from cli_helpers, ensuring comprehensive SHOW command
      coverage via gNMI.

Topology:
    any (works with any topology type)

Fixtures Used:
    - duthosts: Provides access to all DUT hosts
    - localhost: Local host object for operations
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hwsku
    - ptfhost: PTF host for running gNMI client
    - setup_streaming_telemetry: Configures streaming telemetry (parametrized False)
    - gnxi_path: Path to gNMI client tools on PTF
    - request: Pytest request object for dynamic fixture loading
    - skip_non_container_test: Skips test if not running in container environment

Dependencies:
    - pytest: Test framework
    - json: For parsing CLI paths configuration
    - tests.common.helpers.assertions: For test assertions
    - cli_helpers: Custom helper module with setup and verify functions for show commands
    - telemetry_utils: gNMI CLI generation utilities

Notes:
    - gNMI target: SHOW (read-only CLI commands)
    - Supported method: GET only (SUBSCRIBE not supported)
    - CLI paths configuration file: cli_paths.json
    - Each path in cli_paths.json includes:
      - setup: setup function name (if required)
      - setup_fixtures: list of fixtures for setup
      - setup_args: arguments for setup function
      - verify: verification function name
      - verify_args: arguments for verification
    - Example SHOW paths tested:
      - reboot-cause: System reboot reason
      - interfaces: Interface status and counters
      - bgp: BGP protocol information
      - platform: Platform/hardware details
    - Setup functions prepare DUT state before query
    - Verify functions validate gNMI response format and content
    - Tests ensure CLI output is properly formatted for gNMI transport
=============================================================================
"""
import logging
import json
import os
import pytest
from tests.common.helpers.assertions import pytest_assert
import cli_helpers as helper
from telemetry_utils import generate_client_cli

pytestmark = [
    pytest.mark.topology('any')
]

logger = logging.getLogger(__name__)

METHOD_GET = "get"
METHOD_SUBSCRIBE = "subscribe"
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
SHOW_PATHS_FILE = os.path.join(BASE_DIR, "cli_paths.json")


@pytest.mark.parametrize('setup_streaming_telemetry', [False], indirect=True)
def test_telemetry_show_non_get(duthosts, enum_rand_one_per_hwsku_hostname, ptfhost,
                                setup_streaming_telemetry, gnxi_path,
                                request, skip_non_container_test):
    """
    Test non-get mode for SHOW reboot-cause and we exepect failure as SHOW does not support GET
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    logger.info('Start telemetry SHOW testing')
    cmd = generate_client_cli(duthost=duthost, gnxi_path=gnxi_path, method=METHOD_SUBSCRIBE,
                              xpath="reboot-cause", target="SHOW")
    ptf_result = ptfhost.shell(cmd, module_ignore_errors=True)
    pytest_assert(ptf_result['rc'] != 0, "SHOW command {} for non GET operation should fail".format(cmd))


@pytest.mark.parametrize('setup_streaming_telemetry', [False], indirect=True)
def test_telemetry_show_get(duthosts, localhost, enum_rand_one_per_hwsku_hostname, ptfhost,
                            setup_streaming_telemetry, gnxi_path, request,
                            skip_non_container_test):
    """
    Test all SHOW paths from cli_paths.json and execute setup func, gnmi query, and verify func defined in cli_helpers
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    logger.info('Start telemetry SHOW testing')

    with open(SHOW_PATHS_FILE, 'r') as show_paths_file:
        show_paths_data = json.load(show_paths_file)

    for path, test_config in show_paths_data.items():
        # Do any setup that is required before executing query
        if test_config["setup"]:
            setup_fixtures = [request.getfixturevalue(fixture) for fixture in test_config["setup_fixtures"]]
            setup_args = test_config["setup_args"]
            getattr(helper, test_config["setup"])(*setup_fixtures, *setup_args)

        # Execute gnmi get command
        cmd = generate_client_cli(duthost=duthost, gnxi_path=gnxi_path, method=METHOD_GET,
                                  xpath=path, target="SHOW")
        ptf_result = ptfhost.shell(cmd)
        pytest_assert(ptf_result['rc'] == 0, "ptf cmd command {} failed".format(cmd))
        show_gnmi_out = ptf_result['stdout']
        logger.info("GNMI Server output: {}".format(show_gnmi_out))

        # Verify gnmi get with show command
        if test_config["verify"]:
            output = helper.get_json_from_gnmi_output(show_gnmi_out)
            verify_fixtures = [request.getfixturevalue(fixture) for fixture in test_config["verify_fixtures"]]
            verify_args = test_config["verify_args"]
            getattr(helper, test_config["verify"])(*verify_fixtures, *verify_args, output)
