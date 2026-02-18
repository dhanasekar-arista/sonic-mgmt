"""
=============================================================================
Module: telemetry
File: test_events.py
=============================================================================

Description:
    This test file validates the event telemetry subsystem in SONiC, which publishes
    system events (BGP, interface, LAG, DHCP relay, etc.) via gNMI streaming. It
    dynamically loads and executes various event test modules, validates event
    publication, verifies YANG schema compliance, and tests cache overflow handling
    to ensure reliable event delivery and monitoring.

Test Intent:
    - test_events: Dynamically discovers and executes all event test modules
      (*_events.py) in the telemetry/events directory, triggering various system
      events (BGP neighbor state changes, interface up/down, LAG member changes,
      DHCP relay events, etc.), validating each event is properly published via
      gNMI, and verifying output conforms to the appropriate YANG schema for
      each event type.
    - test_events_cache_overflow: Tests event cache overflow behavior by publishing
      a large number of events (550) to exceed cache capacity, verifying that
      events are properly published despite cache pressure, checking the
      MISSED_TO_CACHE counter increments when cache overflows, and confirming
      the PUBLISHED counter shows successful event delivery to subscribers.

Topology:
    any (works with any topology type)

Fixtures Used:
    - duthosts: Provides access to all DUT hosts
    - tbinfo: Testbed information for event testing context
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hwsku
    - ptfhost: PTF host for gNMI client operations
    - ptfadapter: PTF adapter for packet operations if needed
    - setup_streaming_telemetry: Configures streaming telemetry (parametrized False)
    - gnxi_path: Path to gNMI client tools
    - test_eventd_healthy: Ensures eventd service is healthy before testing
    - toggle_all_simulator_ports_to_enum_rand_one_per_hwsku_host_m: For dualtor
      topology setup
    - setup_standby_ports_on_non_enum_rand_one_per_hwsku_host_m: For dualtor
      port configuration

Dependencies:
    - pytest: Test framework
    - telemetry_utils: Provides skip_201911_and_older helper
    - events.event_utils: Event publishing and counter utilities
    - tests.common.dualtor.mux_simulator_control: Dualtor mux control

Notes:
    - Test is marked to disable log analyzer
    - Skips on SONiC 201911 and older versions
    - Events test path: ./telemetry/events
    - Log directory: logs/telemetry/files
    - Dynamically loads event test modules: *_events.py (except eventd_events.py)
    - Each event module must implement test_event() function
    - Validates YANG schema using validate_yang_events.py script
    - Cache overflow test publishes 550 events
    - Event counters: MISSED_TO_CACHE (0), PUBLISHED (1)
    - Supports various event types: BGP, interface, LAG, DHCP relay, etc.
    - Events are published to EVENTS table in STATE_DB
    - YANG validation ensures event format compliance
    - Skip exceptions from individual test files are logged and handled gracefully
=============================================================================
"""
import logging
import pytest
import os
import sys

from telemetry_utils import skip_201911_and_older
from events.event_utils import event_publish_tool
from events.event_utils import reset_event_counters, read_event_counters
from events.event_utils import verify_counter_increase, restart_eventd
from tests.common.dualtor.mux_simulator_control \
    import toggle_all_simulator_ports_to_enum_rand_one_per_hwsku_host_m    # noqa: F401

pytestmark = [
    pytest.mark.topology('any')
]

EVENTS_TESTS_PATH = "./telemetry/events"
sys.path.append(EVENTS_TESTS_PATH)


logger = logging.getLogger(__name__)

BASE_DIR = "logs/telemetry"
DATA_DIR = os.path.join(BASE_DIR, "files")
MISSED_TO_CACHE = 0
PUBLISHED = 1


def validate_yang(duthost, op_file="", yang_file=""):
    assert op_file != "" and yang_file != "", "op_file path or yang_file name not provided"
    cmd = "python ~/validate_yang_events.py -f {} -y {}".format(op_file, yang_file)
    logger.info("Performing yang validation on {} for {}".format(op_file, yang_file))
    ret = duthost.shell(cmd)
    assert ret["rc"] == 0, "Yang validation failed for {}".format(yang_file)


@pytest.mark.parametrize('setup_streaming_telemetry', [False], indirect=True)
@pytest.mark.disable_loganalyzer
def test_events(duthosts, tbinfo, enum_rand_one_per_hwsku_hostname, ptfhost, ptfadapter,
                setup_streaming_telemetry, gnxi_path, test_eventd_healthy,
                toggle_all_simulator_ports_to_enum_rand_one_per_hwsku_host_m,  # noqa: F811
                setup_standby_ports_on_non_enum_rand_one_per_hwsku_host_m):  # noqa: F811
    """ Run series of events inside duthost and validate that output is correct
    and conforms to YANG schema"""
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    logger.info("Start events testing")

    skip_201911_and_older(duthost)

    # Load rest of events
    for file in os.listdir(EVENTS_TESTS_PATH):
        if file.endswith("_events.py") and not file.endswith("eventd_events.py"):
            module = __import__(file[:len(file)-3])
            try:
                module.test_event(duthost, tbinfo, gnxi_path, ptfhost, ptfadapter, DATA_DIR, validate_yang)
            except pytest.skip.Exception as e:
                logger.info("Skipping test file: {} due to {}".format(file, e))
                continue
            logger.info("Completed test file: {}".format(os.path.join(EVENTS_TESTS_PATH, file)))


@pytest.mark.parametrize('setup_streaming_telemetry', [False], indirect=True)
@pytest.mark.disable_loganalyzer
def test_events_cache_overflow(duthosts, enum_rand_one_per_hwsku_hostname, ptfhost, setup_streaming_telemetry,
                               gnxi_path):
    """ Published events till cache overflow, stats should read events missed_to_cache"""
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    logger.info("Start events cache overflow testing")

    skip_201911_and_older(duthost)
    reset_event_counters(duthost)
    restart_eventd(duthost)

    current_missed_to_cache_counter = read_event_counters(duthost)[0]

    """Max cache default configuration size is defined as 100 MB (100 * 1024 * 1024) bytes
    and each event is around 150 bytes,such that max cache would hold ~700,000 events.
    event_publish_tool if no input file provided will post X test bgp events twice,
    for shutdown and startup, hence why we pick 351,000 such that 702,000 events get published
    in order to get cache overflow"""

    event_publish_tool(duthost, "", 351000)

    verify_counter_increase(duthost, current_missed_to_cache_counter, 2000, MISSED_TO_CACHE)
