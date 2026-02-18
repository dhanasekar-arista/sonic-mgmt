"""
=============================================================================
Module: platform_tests
File: test_check_sysfs.py
=============================================================================

Description:
    Mellanox-specific test validating sysfs symbolic links under /var/run/hw-management
    and verifying proper mapping to the pmon container. Covers 'Check SYSFS' test case
    from SONiC platform test plan.

Test Intent:
    - test_check_hw_mgmt_sysfs: Verify symbolic links under /var/run/hw-management are valid
    - test_hw_mgmt_sysfs_mapped_to_pmon: Confirm /var/run/hw-management is mapped to pmon container

Topology:
    Any topology - Mellanox platforms only

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - rand_one_dut_hostname: Selects one random DUT

Dependencies:
    - check_sysfs helper module
    - /var/run/hw-management sysfs hierarchy
    - pmon Docker container

Notes:
    - Test only runs on Mellanox ASIC platforms
    - Validates hw-management sysfs structure integrity
    - Ensures pmon container has same sysfs view as host
    - File list under /var/run/hw-management must match between host and pmon
    - Symbolic link validation prevents broken hardware monitoring
    - Test plan reference: https://github.com/sonic-net/SONiC/blob/master/doc/pmon/sonic_platform_test_plan.md
=============================================================================
"""
import logging
import pytest
from .check_sysfs import check_sysfs

pytestmark = [
    pytest.mark.asic('mellanox'),
    pytest.mark.topology('any')
]


def test_check_hw_mgmt_sysfs(duthosts, rand_one_dut_hostname):
    """This test case is to check the symbolic links under /var/run/hw-management
    """
    duthost = duthosts[rand_one_dut_hostname]
    check_sysfs(duthost)


def test_hw_mgmt_sysfs_mapped_to_pmon(duthosts, rand_one_dut_hostname):
    """This test case is to verify that the /var/run/hw-management folder is mapped to pmon container
    """
    duthost = duthosts[rand_one_dut_hostname]
    logging.info(
        "Verify that the /var/run/hw-management folder is mapped to the pmon container")
    files_under_dut = set(duthost.command(
        "find /var/run/hw-management")["stdout_lines"])
    files_under_pmon = set(duthost.command(
        "docker exec pmon find /var/run/hw-management")["stdout_lines"])
    assert files_under_dut == files_under_pmon, "Folder /var/run/hw-management is not mapped to pmon"
