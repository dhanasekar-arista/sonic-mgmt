"""
=============================================================================
Module: bmp
File: test_frr_bmp_sanity.py
=============================================================================

Description:
    This module tests BMP feature integration with monit monitoring system
    to prevent regression issues. It validates that disabling BMP feature
    does not cause unexpected container logging or monit alerts, ensuring
    proper integration between FRR BMP and system monitoring.

Test Intent:
    - test_frr_bmp_monit_log: Validates that toggling BMP feature state
      (disable then enable) does not trigger unexpected monit logging for
      containers. This test prevents regression of issues where BMP feature
      changes caused false positive alerts or container state mismatches in
      the monit monitoring system.

Topology:
    any, t0-sonic, t1-multi-asic - Works with standard topologies

Fixtures Used:
    - duthosts: Multi-DUT fixture providing access to all DUTs in the testbed
    - enum_frontend_dut_hostname: Enumerates frontend DUT hostnames
    - enum_asic_index: Enumerates ASIC indices for multi-asic platforms

Dependencies:
    - tests.common.helpers.monit: Monit monitoring validation utilities
    - tests.common.utilities: Common test utilities including wait_until
    - bmp.helper: BMP feature enable/disable helper functions
    - config feature state CLI: SONiC CLI for feature state management

Notes:
    - Only runs on virtual switch (vs) device types
    - Test waits up to 180 seconds with 60 second intervals for monit stabilization
    - Regression test added to prevent monit logging issues with BMP state changes
    - Validates proper cleanup and state management during feature toggling
=============================================================================
"""
import pytest
from tests.common.helpers.monit import check_monit_expected_container_logging
from tests.common.utilities import wait_until
from bmp.helper import enable_bmp_feature, disable_bmp_feature

pytestmark = [
    pytest.mark.topology('any', 't0-sonic', 't1-multi-asic'),
    pytest.mark.device_type('vs')
]


def test_frr_bmp_monit_log(duthosts, enum_frontend_dut_hostname, enum_asic_index):
    duthost = duthosts[enum_frontend_dut_hostname]
    disable_bmp_feature(duthost)

    wait_until(180, 60, 0, check_monit_expected_container_logging, duthost)

    enable_bmp_feature(duthost)
