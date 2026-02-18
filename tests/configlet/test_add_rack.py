#! /usr/bin/env python
"""
=============================================================================
Module: configlet
File: test_add_rack.py
=============================================================================

Description:
    Tests the AddRack functionality using configlet and generic config updater.
    AddRack is a scenario for adding a new T0 (Top-of-Rack switch) to a T1 switch
    using configlet-based configuration patching. This test validates that a T0
    can be dynamically added to an existing topology without requiring a full
    minigraph reload, comparing database states before and after the addition.

Test Intent:
    - test_add_rack: Validates adding a T0 switch to a T1 switch using configlet
      strict template (per OneNote documentation). Tests both configlet-based
      addition and generic config updater patch application. Verifies CONFIG-DB,
      APP-DB, and ASIC-DB consistency with original minigraph state, and confirms
      BGP sessions are established for the newly added neighbor.

Topology:
    - t1 (T1 switch topology with at least one T0 neighbor that can be removed
      and re-added)

Fixtures Used:
    - check_image_version: Skips test for SONiC images older than 202111 as
      configlet feature is not available in earlier releases
    - ignore_expected_loganalyzer_exceptions: Ignores expected errors in logs
      during configlet application (sonic_yang validation failures, config errors)
    - configure_dut: Module-scoped fixture that backs up and restores original
      minigraph before and after test execution
    - tbinfo: Provides topology information to determine if backend storage topology
    - duthosts: Multi-DUT host manager
    - rand_one_dut_hostname: Randomly selected DUT hostname for test execution
    - loganalyzer: Log analysis utility for detecting unexpected errors

Dependencies:
    - tests.common.utilities: skip_release for version checking
    - tests.configlet.util.base_test: Core test logic (do_test_add_rack,
      backup_minigraph, restore_orig_minigraph)
    - tests.common.configlet.helpers: Logging utilities (log_info)
    - tests.common.configlet.utils: Database comparison, BGP session validation,
      configlet application utilities
    - tests.configlet.util.strip: Minigraph manipulation for removing T0
    - tests.configlet.util.configlet: Configlet template generation
    - tests.configlet.util.generic_patch: Generic config updater patch operations

Notes:
    - Test is marked with @pytest.mark.disable_loganalyzer as configlet application
      intentionally generates validation errors during intermediate states
    - Requires SONiC version 202205 or later (skips 201811, 201911, 202012, 202106, 202111)
    - Test performs destructive operations: removes T0 from minigraph, applies
      configlet to re-add it, and validates end state matches original
    - Configlet test is currently skipped (skip_clet_test=True) due to known issues
    - Generic config updater path is tested as primary validation method
    - Test creates multiple database snapshots in logs/configlet/AddRack directory
    - BGP session verification includes both IPv4 and IPv6 neighbor addresses
    - Storage backend topologies are specially handled via is_storage_backend flag

Git History:
    579f7ba37 - Refactor shared scripts under configlet to common place
    dab77c420 - Remove TACACS fixture from none TACACS test cases
    07f328770 - Enable TACACS on test cases
    7c189afca - Skip clet test
    3064c033a - Python3 migration with bug fix
=============================================================================
"""

import pytest
import sys
from tests.common.utilities import skip_release
from .util.base_test import do_test_add_rack, backup_minigraph, restore_orig_minigraph
from tests.common.configlet.helpers import log_info

pytestmark = [
        pytest.mark.topology("t1")
        ]


@pytest.fixture(scope="module", autouse=True)
def check_image_version(duthosts, rand_one_dut_hostname):
    """Skips this test if the SONiC image installed on DUT is older than 202111

    Args:
        duthost: DUT host object.

    Returns:
        None.
    """
    duthost = duthosts[rand_one_dut_hostname]
    skip_release(duthost, ["201811", "201911", "202012", "202106", "202111"])


@pytest.fixture(autouse=True)
def ignore_expected_loganalyzer_exceptions(duthosts, rand_one_dut_hostname, loganalyzer):
    """
       Ignore expected errors in logs during test execution

       Args:
           loganalyzer: Loganalyzer utility fixture
           duthost: DUT host object
    """
    duthost = duthosts[rand_one_dut_hostname]
    if loganalyzer:
        loganalyzer_ignore_regex = [
            ".*ERR sonic_yang: Data Loading Failed:Must condition not satisfied.*",
            ".*ERR sonic_yang: Failed to validate data tree#012.*",
            ".*ERR config: Change Applier:.*",
        ]
        loganalyzer[duthost.hostname].ignore_regex.extend(loganalyzer_ignore_regex)

    yield


@pytest.fixture(scope="module")
def configure_dut(duthosts, rand_one_dut_hostname):
    try:
        log_info("configure_dut fixture on setup for {}".format(rand_one_dut_hostname))
        if not restore_orig_minigraph(duthosts[rand_one_dut_hostname]):
            backup_minigraph(duthosts[rand_one_dut_hostname])
        log_info("configure_dut fixture DONE for {}".format(rand_one_dut_hostname))
        yield
    finally:
        log_info("configure_dut fixture on cleanup for {}".format(rand_one_dut_hostname))
        restore_orig_minigraph(duthosts[rand_one_dut_hostname])
        log_info("configure_dut fixture DONE for {}".format(rand_one_dut_hostname))


@pytest.mark.disable_loganalyzer
def test_add_rack(configure_dut, tbinfo, duthosts, rand_one_dut_hostname):
    global data_dir, orig_db_dir, clet_db_dir, files_dir

    duthost = duthosts[rand_one_dut_hostname]

    log_info("sys.version={}".format(sys.version))
    do_test_add_rack(duthost, is_storage_backend='backend' in tbinfo['topo']['name'], skip_clet_test=True)
