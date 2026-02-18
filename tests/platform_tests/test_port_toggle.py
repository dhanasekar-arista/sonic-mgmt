"""
=============================================================================
Module: platform_tests
File: test_port_toggle.py
=============================================================================

Description:
    Tests port toggle functionality in SONiC. Validates that interfaces can be
    flapped (shutdown/startup) and come back up operational.

Test Intent:
    - test_port_toggle: Validate all DUT interfaces can be toggled and return to up state

Topology:
    Any topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one frontend DUT per hardware SKU
    - bring_up_dut_interfaces: Ensures all interfaces are up before test
    - tbinfo: Testbed information

Dependencies:
    - port_toggle helper function from tests.common

Notes:
    - Test flaps all interfaces on DUT one by one
    - Validates all interfaces are up correctly after toggle
    - Uses bring_up_dut_interfaces fixture to ensure clean starting state
    - Loganalyzer disabled (expected error logs during interface flaps)
    - Pass criteria: All interfaces operational post-toggle
=============================================================================
"""

import pytest

from tests.common import port_toggle


pytestmark = [
    pytest.mark.topology("any"),
    pytest.mark.disable_loganalyzer,
]


class TestPortToggle(object):
    """
    TestPortToggle class for testing port toggle
    """

    def test_port_toggle(self, duthosts, enum_rand_one_per_hwsku_frontend_hostname, bring_up_dut_interfaces, tbinfo):
        """
        Validates that port toggle works as expected

        Test steps:
            1.) Flap all interfaces on DUT one by one.
            2.) Verify interfaces are up correctly.

        Pass Criteria: All interfaces are up correctly.
        """
        duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
        port_toggle(duthost, tbinfo)
