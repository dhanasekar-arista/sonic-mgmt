"""
=============================================================================
Module: platform_tests
File: test_hw_management_service.py
=============================================================================

Description:
    Mellanox-specific test verifying that the hw-management service is running
    properly. Ensures critical hardware management daemon is active and functional.

Test Intent:
    - test_hw_management_service_status: Verify hw-management systemd service is active and running

Topology:
    Any topology - Mellanox platforms only

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - rand_one_dut_hostname: Selects one random DUT

Dependencies:
    - check_hw_mgmt_service helper module
    - hw-management systemd service

Notes:
    - Test only runs on Mellanox ASIC platforms
    - hw-management service controls thermal management, LED control, and sensor monitoring
    - Service failure can cause platform instability
    - Test plan reference: https://github.com/sonic-net/SONiC/blob/master/doc/pmon/sonic_platform_test_plan.md
=============================================================================
"""
import pytest
from .check_hw_mgmt_service import check_hw_management_service

pytestmark = [
    pytest.mark.asic('mellanox'),
    pytest.mark.topology('any')
]


def test_hw_management_service_status(duthosts, rand_one_dut_hostname):
    """This test case is to verify that the hw-management service is running properly
    """
    duthost = duthosts[rand_one_dut_hostname]
    check_hw_management_service(duthost)
