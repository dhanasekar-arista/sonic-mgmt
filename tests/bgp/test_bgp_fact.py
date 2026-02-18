"""
=============================================================================
Module: bgp
File: test_bgp_fact.py
=============================================================================

Description:
    Tests BGP facts collection functionality to ensure BGP state information
    can be properly retrieved and validated. This is a basic sanity test for
    BGP operational status.

Test Intent:
    - test_bgp_facts: Validates BGP facts can be successfully collected from
      the DUT, ensuring BGP sessions are established and basic BGP information
      is accessible

Topology:
    any, t0-sonic, t1-multi-asic

Fixtures Used:
    - duthosts: Multi-DUT fixture
    - enum_frontend_dut_hostname: Frontend DUT enumeration
    - enum_asic_index: ASIC instance enumeration for multi-ASIC support

Dependencies:
    - tests.common.helpers.bgp.run_bgp_facts

Notes:
    - Only runs on virtual switch (vs) device types
    - Supports multi-ASIC configurations
    - Basic sanity test for BGP operational status
    - Can run on any topology type
=============================================================================
"""

import pytest
from tests.common.helpers.bgp import run_bgp_facts

pytestmark = [
    pytest.mark.topology('any', 't0-sonic', 't1-multi-asic'),
    pytest.mark.device_type('vs')
]


def test_bgp_facts(duthosts, enum_frontend_dut_hostname, enum_asic_index):
    run_bgp_facts(duthosts[enum_frontend_dut_hostname], enum_asic_index)
