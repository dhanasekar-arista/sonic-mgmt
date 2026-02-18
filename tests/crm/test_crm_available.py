"""
Module: tests.crm.test_crm_available
File: test_crm_available.py

Description:
    This module contains tests for validating CRM (Critical Resource Monitoring)
    nexthop group resource availability across different hardware SKUs. It ensures
    that the total available nexthop groups meet platform-specific thresholds.

Test Intent:
    - Verify that the total count of nexthop groups (used + available) meets or
      exceeds platform-specific minimum thresholds
    - Validate that different hardware SKUs have appropriate nexthop group capacity
    - Ensure CRM resource reporting is accurate for nexthop group resources
    - Test platform-specific resource constraints (e.g., Arista, Nokia SKUs)

Topology:
    Supported topologies: t0, t1, m0, mx, m1
    - Requires at least one frontend DUT with active interfaces
    - No specific neighbor or link requirements

Fixtures Used:
    - duthosts: Fixture providing access to all DUTs in the testbed
    - enum_rand_one_per_hwsku_frontend_hostname: Randomly selects one frontend DUT
      per hardware SKU for test execution
    - crm_resources: Module-scoped fixture that retrieves CRM resource statistics
      from 'crm show resources all' command

Dependencies:
    - tests.common.helpers.assertions: For pytest assertions
    - CRM daemon must be running and reporting valid statistics
    - Platform-specific SKU thresholds defined in SKU_NEXTHOP_THRESHOLDS

Notes:
    - SKU_NEXTHOP_THRESHOLDS defines platform-specific minimum nexthop group counts
    - Default threshold is 256 if SKU is not in the defined mapping
    - Test validates total capacity (used + available), not just available count
    - Case-insensitive SKU matching is performed for threshold lookup
    - History: Added nexthop threshold tests for various Arista and Nokia platforms
    - Recent changes include support for 7215A1, 7050C SKUs and enhanced M1 support
"""

import pytest
import logging
from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.topology('t0', 't1', 'm0', 'mx', 'm1'),
]

logger = logging.getLogger(__name__)

NEXTHOP_GROUP_TOTAL = 256

SKU_NEXTHOP_THRESHOLDS = {
    'arista-720dt-g48s4': 15,
    'nokia-m0-7215': 126,
    'nokia-7215-a1': 126,
    'nokia-7215-a1-g48s4': 126,
    'nokia-7215-a1-mgx-g48s4': 126,
    'nokia-7215': 126,
    'arista-7050cx3-32s-c28s4': 255,
    'Arista-7050CX3-32S-C32': 255,
    'arista-7050cx3-32s-s128': 255,
    'arista-7050cx3-32s-c6s104': 255,
    'arista-7050cx3-32s-c28s16': 255,
    'arista-7050cx3-32c-c28s4': 255,
    'Arista-7050CX3-32c-C32': 255,
    'arista-7050cx3-32c-s128': 255,
    'arista-7050cx3-32c-c6s104': 255,
    'arista-7050cx3-32c-c28s16': 255,
}

DEFAULT_NEXTHOP_THRESHOLD = 256


def test_crm_next_hop_group(duthosts, enum_rand_one_per_hwsku_frontend_hostname, crm_resources):
    """
    test that runs `crm show resources` and parses next-hop group usage.
    """
    # Example check: ensure next-hop group usage is below a certain threshold
    # This is a placeholder for the actual resource name; adjust as needed
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]

    hwsku = duthost.facts["hwsku"].lower()
    lower_sku_nexthop_thresholds = {k.lower(): v for k, v in SKU_NEXTHOP_THRESHOLDS.items()}
    nexthop_group_threshold = lower_sku_nexthop_thresholds.get(hwsku, DEFAULT_NEXTHOP_THRESHOLD)

    resource_name = "nexthop_group"
    if resource_name in crm_resources:
        used = crm_resources[resource_name]["used"]
        available = crm_resources[resource_name]["available"]
        total = used + available
        pytest_assert(total >= nexthop_group_threshold,
                      f"next-hop groups ({total}) should be greater than or equal to {nexthop_group_threshold} on platform '{hwsku}'") # noqa
    else:
        pytest.fail(f"Resource '{resource_name}' not found in CRM resources output on platform '{hwsku}'.")
