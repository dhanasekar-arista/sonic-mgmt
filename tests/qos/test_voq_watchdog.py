"""
=============================================================================
Module: qos
File: test_voq_watchdog.py
=============================================================================

Description:
    SAI thrift-based tests for the VoQ (Virtual Output Queue) watchdog feature
    in SONiC. Validates that the VoQ watchdog mechanism properly detects stuck
    queues and triggers appropriate recovery actions when enabled.

Test Intent:
    - testVoqWatchdog: Parameterized test that validates VoQ watchdog behavior
      with watchdog both enabled and disabled. Blocks VoQ0 by setting credit_pir
      to 0, sends traffic, and verifies that stuck VoQ is detected when watchdog
      is enabled but not when disabled. Tests recovery by unblocking queue and
      running TrafficSanityTest.

Topology:
    any topology

Fixtures Used:
    - check_skip_voq_watchdog_test: Class-scoped autouse fixture that skips test
      if VoQ watchdog is not enabled on the DUT
    - ignore_log_voq_watchdog: Function-scoped autouse fixture that adds ignore
      patterns for HARDWARE_WATCHDOG, soft_reset, and VOQ stuck messages
    - dutTestParams: DUT host test parameters
    - dutConfig: DUT configuration including interfaces, test port IDs/IPs
    - dutQosConfig: DUT QoS configuration map
    - get_src_dst_asic_and_duts: Source and destination ASIC/DUT information

Dependencies:
    - tests.qos.qos_helpers: voq_watchdog_enabled, modify_voq_watchdog functions
    - tests.qos.qos_sai_base.QosSaiBase: Base class for QoS SAI tests
    - SAI thrift library: For queue manipulation and counter reading

Notes:
    - Requires RPC syncd image (--qos_swap_syncd=True by default)
    - Uses PTF test case: sai_qos_tests.VoqWatchdogTest
    - Sends 100 packets per test iteration (PKTS_NUM = 100)
    - Packet size: 1350 bytes, DSCP: 8, Queue: 0
    - Parameterized with enable_voq_watchdog=[True, False]
    - Always re-enables watchdog in finally block if it was disabled
    - Validates system recovery with TrafficSanityTest after unblock
=============================================================================
"""

import logging
import pytest

from tests.common.fixtures.duthost_utils import dut_qos_maps, \
    separated_dscp_to_tc_map_on_uplink                                                      # noqa: F401
from tests.common.fixtures.ptfhost_utils import copy_ptftests_directory                     # noqa: F401
from tests.common.fixtures.ptfhost_utils import copy_saitests_directory                     # noqa: F401
from tests.common.fixtures.ptfhost_utils import change_mac_addresses                        # noqa: F401
from .qos_helpers import voq_watchdog_enabled, modify_voq_watchdog
from .qos_sai_base import QosSaiBase

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]

PKTS_NUM = 100


@pytest.fixture(scope="function", autouse=True)
def ignore_log_voq_watchdog(duthosts, loganalyzer):
    if not loganalyzer:
        yield
        return
    ignore_list = [r".*HARDWARE_WATCHDOG.*", r".*soft_reset*", r".*VOQ Appears to be stuck*"]
    for dut in duthosts:
        for line in ignore_list:
            loganalyzer[dut.hostname].ignore_regex.append(line)
    yield
    return


class TestVoqWatchdog(QosSaiBase):
    """TestVoqWatchdog derives from QosSaiBase and contains collection of VOQ watchdog test cases.
    """
    @pytest.fixture(scope="class", autouse=True)
    def check_skip_voq_watchdog_test(self, get_src_dst_asic_and_duts):
        if not voq_watchdog_enabled(get_src_dst_asic_and_duts):
            pytest.skip("Voq watchdog test is skipped since voq watchdog is not enabled.")

    @pytest.mark.parametrize("enable_voq_watchdog", [True, False])
    def testVoqWatchdog(
            self, ptfhost, dutTestParams, dutConfig, dutQosConfig,
            duthosts, get_src_dst_asic_and_duts, enable_voq_watchdog
    ):
        """
            Test VOQ watchdog
            Args:
                ptfhost (AnsibleHost): Packet Test Framework (PTF)
                dutTestParams (Fixture, dict): DUT host test params
                dutConfig (Fixture, dict): Map of DUT config containing dut interfaces, test port IDs, test port IPs,
                    and test ports
                dutQosConfig (Fixture, dict): Map containing DUT host QoS configuration
                enable_voq_watchdog (bool): Whether to enable or disable VOQ watchdog during the test
            Returns:
                None
            Raises:
                RunAnsibleModuleFail if ptf test fails
        """

        try:
            if not enable_voq_watchdog:
                modify_voq_watchdog(duthosts, get_src_dst_asic_and_duts, enable=False)

            testParams = dict()
            testParams.update(dutTestParams["basicParams"])
            testParams.update({
                "dscp": 8,
                "queue_idx": 0,
                "dst_port_id": dutConfig["testPorts"]["dst_port_id"],
                "dst_port_ip": dutConfig["testPorts"]["dst_port_ip"],
                "src_port_id": dutConfig["testPorts"]["src_port_id"],
                "src_port_ip": dutConfig["testPorts"]["src_port_ip"],
                "src_port_vlan": dutConfig["testPorts"]["src_port_vlan"],
                "packet_size": 1350,
                "pkts_num": PKTS_NUM,
                "voq_watchdog_enabled": enable_voq_watchdog,
                "dutInterfaces": dutConfig["dutInterfaces"],
                "testPorts": dutConfig["testPorts"],
            })

            self.runPtfTest(
                ptfhost, testCase="sai_qos_tests.VoqWatchdogTest",
                testParams=testParams)

            self.runPtfTest(
                ptfhost, testCase="sai_qos_tests.TrafficSanityTest",
                testParams=testParams)

        finally:
            if not enable_voq_watchdog:
                modify_voq_watchdog(duthosts, get_src_dst_asic_and_duts, enable=True)
