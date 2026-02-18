"""
=============================================================================
Module: platform_tests
File: test_idle_driver.py
=============================================================================

Description:
    Tests CPU idle driver configuration. Validates that devices with potential idle
    state problems have idle drivers disabled or limited to C-state 1 or lower.
    Prevents system instability from deep CPU idle states.

Test Intent:
    - test_idle_driver: Verify idle driver is disabled or max C-state <= 1

Topology:
    M0, MX topologies

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hardware SKU

Dependencies:
    - /sys/devices/system/cpu/cpuidle/current_driver for driver detection
    - /sys/devices/system/cpu/cpu*/cpuidle/state*/name for C-state enumeration

Notes:
    - Test expects current_driver to be "none" (disabled) OR max C-state <= 1
    - C-states: C0 (active), C1 (halt), C2+ (deeper idle states)
    - Some devices have bugs in deeper C-states causing instability
    - Test parses C-state values from sysfs state names
    - If idle driver present, validates no CPU has C-state > 1 available
    - Intel idle driver and ACPI idle driver should both be disabled on problematic platforms
    - Test only runs on M0, MX topologies (chassis platforms)
=============================================================================
"""
import logging
import pytest

from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('m0', 'mx', 'c0'),
]


def test_idle_driver(duthosts, enum_rand_one_per_hwsku_hostname):
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    idle_driver_result = duthost.shell('cat /sys/devices/system/cpu/cpuidle/current_driver', module_ignore_errors=True)
    if idle_driver_result['rc'] == 0 and idle_driver_result['stdout'] != "none":
        cstates = duthost.shell('sed -n "s/.*C\\([0-9]*\\).*/\\1/p" '
                                '/sys/devices/system/cpu/cpu*/cpuidle/state*/name')['stdout'].split()
        max_cstate = max([int(cstate) for cstate in cstates])
        pytest_assert(max_cstate <= 1,
                      "When idle driver is present, cstate>1 is not allowed: max_cstate {}"
                      .format(max_cstate))
