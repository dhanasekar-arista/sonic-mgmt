"""
=============================================================================
Module: qos
File: test_oq_watchdog.py
=============================================================================

Description:
    SAI thrift-based tests for the OQ (Output Queue) watchdog feature in
    SONiC. Validates that the OQ watchdog mechanism properly detects and
    responds to queue stalls/hangs by triggering recovery actions.

Test Intent:
    - testOqWatchdog: Verifies OQ watchdog functionality by intentionally
      blocking queues and confirming watchdog triggers as expected. Blocks
      VoQ7 by setting credit_pir to 0, fills Q7 leakout with ping traffic,
      blocks OQ0 by setting transmit_pir to 0, sends traffic on Q0, and
      validates that OQ watchdog triggers within ~5 seconds. Then unblocks
      queues and runs TrafficSanityTest to verify system recovery.

Topology:
    any topology

Fixtures Used:
    - check_skip_oq_watchdog_test: Class-scoped autouse fixture that skips
      test if OQ watchdog is not enabled on the DUT
    - ignore_log_oq_watchdog: Function-scoped fixture that adds ignore regex
      patterns for expected HARDWARE_WATCHDOG and soft_reset log messages
    - disable_voq_watchdog_function_scope: Disables VoQ watchdog during test
    - dutTestParams: DUT host test parameters
    - dutConfig: DUT configuration including interfaces, test port IDs/IPs
    - dutQosConfig: DUT QoS configuration map
    - get_src_dst_asic_and_duts: Source and destination ASIC/DUT information

Dependencies:
    - tests.common.fixtures.duthost_utils: DUT QoS maps and DSCP utilities
    - tests.common.fixtures.ptfhost_utils: PTF test directory and MAC utilities
    - tests.qos.qos_sai_base.QosSaiBase: Base class for QoS SAI tests
    - SAI thrift library: For queue manipulation and counter reading

Notes:
    - Requires RPC syncd image (--qos_swap_syncd=True by default)
    - Uses PTF test cases: sai_qos_tests.OqWatchdogTest and TrafficSanityTest
    - Sends 100 packets per test iteration (PKTS_NUM = 100)
    - Packet size: 1350 bytes, DSCP: 8, Queue: 0
    - Blocks VoQ7 first to prevent dequeue/enqueue
    - Uses ping with 50 packets at interval 0 to fill Q7 leakout
    - Multi-ASIC support via namespace-specific ping commands
    - Always unblocks queues in finally block to ensure cleanup
    - Validates system recovery with TrafficSanityTest after unblock
=============================================================================
"""

import logging
import pytest

from tests.common.fixtures.duthost_utils import dut_qos_maps, \
    separated_dscp_to_tc_map_on_uplink                                                      # noqa F401
from tests.common.fixtures.ptfhost_utils import copy_ptftests_directory                     # noqa F401
from tests.common.fixtures.ptfhost_utils import copy_saitests_directory                     # noqa F401
from tests.common.fixtures.ptfhost_utils import change_mac_addresses                        # noqa F401
from .qos_sai_base import QosSaiBase

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any')
]

PKTS_NUM = 100


@pytest.fixture(scope="function")
def ignore_log_oq_watchdog(duthosts, loganalyzer):
    if not loganalyzer:
        yield
        return
    ignore_list = [r".*HARDWARE_WATCHDOG.*", r".*soft_reset*"]
    for dut in duthosts:
        for line in ignore_list:
            loganalyzer[dut.hostname].ignore_regex.append(line)
    yield
    return


class TestOqWatchdog(QosSaiBase):
    """TestVoqWatchdog derives from QosSaiBase and contains collection of OQ watchdog test cases.
    """
    @pytest.fixture(scope="class", autouse=True)
    def check_skip_oq_watchdog_test(self, get_src_dst_asic_and_duts):
        if not self.oq_watchdog_enabled(get_src_dst_asic_and_duts):
            pytest.skip("OQ watchdog test is skipped since OQ watchdog is not enabled.")

    def testOqWatchdog(
            self, ptfhost, dutTestParams, dutConfig, dutQosConfig,
            get_src_dst_asic_and_duts, ignore_log_oq_watchdog,
            disable_voq_watchdog_function_scope
    ):
        """
            Test OQ watchdog functionality.
            Test steps:
                1. block voq7, sys_port scheduler set Q7 credit_pir to 0
                2. fill leakout of Q7 by ping, make sure no packet dequeue/enqueue in OQ7 afterwards
                3. block oq0, sys_port scheduler set Q0 transmit_pir to 0
                4. send traffic on Q0, oq watchdog should be triggered in about 5 seconds
                5. Unblock voq7 and oq0 to restore the system state
                6. Run TrafficSanityTest to verify the system state is restored
            Args:
                ptfhost (AnsibleHost): Packet Test Framework (PTF)
                dutTestParams (Fixture, dict): DUT host test params
                dutConfig (Fixture, dict): Map of DUT config containing dut interfaces, test port IDs, test port IPs,
                    and test ports
                dutQosConfig (Fixture, dict): Map containing DUT host QoS configuration
            Returns:
                None
            Raises:
                RunAnsibleModuleFail if ptf test fails
        """

        dst_dut = get_src_dst_asic_and_duts['dst_dut']
        dst_asic_index = get_src_dst_asic_and_duts['dst_asic_index']
        dst_port = dutConfig['dutInterfaces'][dutConfig["testPorts"]["dst_port_id"]]
        interfaces = self.get_port_channel_members(dst_dut, dst_port)

        testParams = dict()
        testParams.update(dutTestParams["basicParams"])
        testParams.update({
            "dscp": 8,
            "queue_id": 0,
            "dst_port_id": dutConfig["testPorts"]["dst_port_id"],
            "dst_port_ip": dutConfig["testPorts"]["dst_port_ip"],
            "dst_interfaces": interfaces,
            "src_port_id": dutConfig["testPorts"]["src_port_id"],
            "src_port_ip": dutConfig["testPorts"]["src_port_ip"],
            "src_port_vlan": dutConfig["testPorts"]["src_port_vlan"],
            "packet_size": 1350,
            "pkts_num": PKTS_NUM,
            "oq_watchdog_enabled": True,
        })

        # Run TrafficSanityTest to verify the system in good state before starting the test
        self.runPtfTest(
            ptfhost, testCase="sai_qos_tests.TrafficSanityTest",
            testParams=testParams)

        try:
            # Block voq7
            original_pir_voq7 = self.block_queue(dst_dut, dst_port, 7, "voq", dst_asic_index)
            # Fill leakout of Q7 by ping
            dst_port_ip = dutConfig["testPorts"]["dst_port_ip"]
            cmd_opt = "sudo ip netns exec asic{}".format(dst_asic_index)
            if not dst_dut.sonichost.is_multi_asic:
                cmd_opt = ""
            dst_dut.shell("{} ping -I {} -c 50 {} -i 0 -w 0 || true".format(cmd_opt, dst_port, dst_port_ip))

            # Block oq0
            original_pir_oq0 = self.block_queue(dst_dut, dst_port, 0, "oq", dst_asic_index)

            self.runPtfTest(
                ptfhost, testCase="sai_qos_tests.OqWatchdogTest",
                testParams=testParams)

        finally:
            # Unblock voq7 and oq0 to restore the system state
            self.unblock_queue(dst_dut, dst_port, 7, "voq", original_pir_voq7, dst_asic_index)
            self.unblock_queue(dst_dut, dst_port, 0, "oq", original_pir_oq0, dst_asic_index)

            self.runPtfTest(
                ptfhost, testCase="sai_qos_tests.TrafficSanityTest",
                testParams=testParams)
