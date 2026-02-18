"""
Module: tests.cpu_shaper.test_cpu_shaper
File: test_cpu_shaper.py

Description:
    This test module validates CPU queue shaper configuration on Broadcom platforms.
    CPU queue shapers are hardware configurations that rate-limit traffic sent to the
    CPU to prevent CPU overload. This test verifies that the shaper configuration
    persists correctly across various system reboot scenarios.

Test Intent:
    - Validate CPU queue shaper configuration on Broadcom ASIC platforms
    - Ensure shaper settings persist across different reboot types (cold, warm, fast, soft)
    - Verify that CPU queues 0 and 7 maintain expected PPS (packets per second) limits of 600
    - Confirm configuration consistency after critical processes restart

    NOTE: Mellanox and Cisco platforms do not have CPU shaper configurations and are
    excluded from this test via ASIC-specific pytest markers.

Topology:
    - t0, t1 topologies (specified via pytest.mark.topology)
    - Broadcom ASIC only (specified via pytest.mark.asic)
    - Single DUT selected randomly per hardware SKU using enum_rand_one_per_hwsku_frontend_hostname

Fixtures Used:
    - duthosts: Collection of all DUT hosts in the testbed
    - localhost: The local host fixture for orchestrating reboots
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one random frontend DUT per hardware SKU
    - request: Pytest request fixture to access command-line options

Dependencies:
    - tests.common.config_reload: Provides config_reload() for device configuration restoration
    - tests.common.reboot: Provides reboot() function for various reboot operations
    - tests.common.platform.processes_utils: Provides wait_critical_processes() for service readiness
    - cpu_shaper/scripts/get_shaper.c: Broadcom CINT script to query CPU queue shaper settings
    - bcmcmd: Broadcom command-line tool available in syncd container

Notes:
    - Test uses loganalyzer disable marker to prevent false positives during reboot
    - Reboot type is configurable via --cpu_shaper_reboot_type command-line option (default: cold)
    - The test copies a CINT script to the syncd container to query shaper configuration
    - Expected configuration: CPU queues 0 and 7 should have 600 PPS max rate
    - Cleanup is performed in finally block to remove temporary CINT script
    - Config reload is performed at the end to restore device to clean state

Git History:
    bcbc14bbb Add a test for verifying cpu queue shaper config (#17299)

"""

import logging
import pytest
import re

from tests.common import config_reload
from tests.common.reboot import reboot
from tests.common.platform.processes_utils import wait_critical_processes

pytestmark = [
    pytest.mark.topology("t0", "t1"),
    pytest.mark.asic("broadcom")
]

logger = logging.getLogger(__name__)

BCM_CINT_FILENAME = "get_shaper.c"
DEST_DIR = "/tmp"
CMD_GET_SHAPER = "bcmcmd 'cint {}'".format(BCM_CINT_FILENAME)


def verify_cpu_queue_shaper(dut):
    """
    Verify cpu queue shaper configuration is as expected

    Args:
        dut (SonicHost): The target device
    """
    # Copy cint script to /tmp on the device
    dut.copy(src="cpu_shaper/scripts/{}".format(BCM_CINT_FILENAME), dest=DEST_DIR)

    # Copy cint script to the syncd container
    dut.shell("docker cp {}/{} syncd:/".format(DEST_DIR, BCM_CINT_FILENAME))

    # Execute the cint script and parse the output
    res = dut.shell(CMD_GET_SHAPER)['stdout']

    # Expected shaper PPS configuration for CPU queues 0, and 7
    expected_pps = {0: 600, 7: 600}
    pattern = r'cos=(\d+) pps_max=(\d+)'
    matches = re.findall(pattern, res)
    actual_pps = {int(cos): int(pps) for cos, pps in matches}
    assert (expected_pps == actual_pps)


@pytest.mark.disable_loganalyzer
def test_cpu_queue_shaper(duthosts, localhost, enum_rand_one_per_hwsku_frontend_hostname, request):
    """
    Validates the cpu queue shaper configuration after reboot(reboot, warm-reboot)

    """
    try:
        duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
        reboot_type = request.config.getoption("--cpu_shaper_reboot_type")

        # Perform reboot as specified via the reboot_type parameter
        logger.info("Do {} reboot".format(reboot_type))
        reboot(duthost, localhost, reboot_type=reboot_type, reboot_helper=None, reboot_kwargs=None)

        # Wait for critical processes to be up
        wait_critical_processes(duthost)
        logger.info("Verify cpu queue shaper config after {} reboot".format(reboot_type))

        # Verify cpu queue shaper configuration
        verify_cpu_queue_shaper(duthost)

    finally:
        duthost.shell("rm {}/{}".format(DEST_DIR, BCM_CINT_FILENAME))
        config_reload(duthost)
