"""
=============================================================================
Module: layer1
File: test_port_error.py
=============================================================================

Description:
    This test validates MAC fault detection and tracking on SONiC devices.
    It tests the ability to detect and count MAC local and remote faults by
    manipulating SFP module RX/TX outputs and verifying that fault counters
    increment correctly when interfaces experience link failures.

Test Intent:
    - test_mac_local_fault_increment: Validates that MAC local fault counters
      increment when the RX optical output is disabled and re-enabled on an
      interface. This simulates loss of receive signal and verifies the device
      properly detects and counts local faults.
    - test_mac_remote_fault_increment: Validates that MAC remote fault counters
      increment when the TX optical output is disabled and re-enabled on an
      interface. This simulates the remote end losing signal and verifies the
      device properly detects and counts remote faults received from peers.

Topology:
    PTP topology required (test skips for non-PTP topologies)

Fixtures Used:
    - is_supported_platform: Automatically checks if the DUT platform is
      supported and verifies SONiC release compatibility. Skips test if
      platform is unsupported or release is too old.
    - select_random_interfaces: Selects up to 5 random interfaces with SFP
      modules present for testing
    - duthosts: Provides list of DUT hosts for testing
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one random frontend
      DUT per hardware SKU
    - tbinfo: Testbed information used to verify PTP topology

Dependencies:
    - tests.common.helpers.assertions: For pytest assertions
    - tests.common.utilities: For skip_release functionality

Notes:
    - Supported platforms: arista_7060x6, nvidia_sn5640, nvidia_sn5600
    - Requires PTP topology, skips for other topologies
    - Skips for SONiC releases: 201811, 201911, 202012, 202205, 202211, 202305, 202405
    - Uses sfputil debug commands to manipulate RX/TX optical outputs
    - Waits 5 seconds after disabling interface and 20 seconds after enabling
    - Validates interface status transitions: up -> down -> up
    - Requires at least one interface with SFP module present
    - Tests up to 5 randomly selected interfaces per test run
    - Disables log analyzer to prevent interference with fault injection testing
=============================================================================
"""
import logging
import pytest
import random
import time

from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import skip_release

pytestmark = [
    pytest.mark.disable_loganalyzer,  # disable automatic loganalyzer
    pytest.mark.topology('any')
]

SUPPORTED_PLATFORMS = ["arista_7060x6", "nvidia_sn5640", "nvidia_sn5600"]
cmd_sfp_presence = "sudo sfpshow presence"


class TestMACFault(object):
    @pytest.fixture(autouse=True)
    def is_supported_platform(self, duthost, tbinfo):
        if 'ptp' not in tbinfo['topo']['name']:
            pytest.skip("Skipping test: Not applicable for non-PTP topology")

        if any(platform in duthost.facts['platform'] for platform in SUPPORTED_PLATFORMS):
            skip_release(duthost, ["201811", "201911", "202012", "202205", "202211", "202305", "202405"])
        else:
            pytest.skip("DUT has platform {}, test is not supported".format(duthost.facts['platform']))

    @staticmethod
    def get_mac_fault_count(dut, interface, fault_type):
        output = dut.show_and_parse("show int errors {}".format(interface))
        logging.info("Raw output for show int errors on {}: {}".format(interface, output))

        fault_count = 0
        for error_info in output:
            if error_info['port errors'] == fault_type:
                fault_count = int(error_info['count'])
                break

        logging.info("{} count on {}: {}".format(fault_type, interface, fault_count))
        return fault_count

    @staticmethod
    def get_interface_status(dut, interface):
        return dut.show_and_parse("show interfaces status {}".format(interface))[0].get("oper", "unknown")

    @pytest.fixture
    def select_random_interfaces(self, duthosts, enum_rand_one_per_hwsku_frontend_hostname):
        dut = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
        interfaces = list(dut.show_and_parse("show interfaces status"))

        sfp_presence = dut.command(cmd_sfp_presence)
        parsed_presence = {line.split()[0]: line.split()[1] for line in sfp_presence["stdout_lines"][2:]}

        available_interfaces = [
            intf["interface"] for intf in interfaces
            if parsed_presence.get(intf["interface"]) == "Present"
        ]

        pytest_assert(available_interfaces, "No interfaces with SFP detected. Cannot proceed with tests.")

        # Select 5 random interfaces (or fewer if not enough available)
        selected_interfaces = random.sample(available_interfaces, min(5, len(available_interfaces)))

        return dut, selected_interfaces

    def test_mac_local_fault_increment(self, select_random_interfaces):
        dut, interfaces = select_random_interfaces

        for interface in interfaces:
            pytest_assert(self.get_interface_status(dut, interface) == "up",
                          "Interface {} was not up before disabling/enabling rx-output using sfputil".format(interface))

            local_fault_before = self.get_mac_fault_count(dut, interface, "mac local fault")
            logging.info("Initial MAC local fault count on {}: {}".format(interface, local_fault_before))

            dut.shell("sudo sfputil debug rx-output {} disable".format(interface))
            time.sleep(5)
            pytest_assert(self.get_interface_status(dut, interface) == "down",
                          "Interface {} did not go down after disabling rx-output using sfputil".format(interface))

            dut.shell("sudo sfputil debug rx-output {} enable".format(interface))
            time.sleep(20)
            pytest_assert(self.get_interface_status(dut, interface) == "up",
                          "Interface {} did not come up after enabling rx-output using sfputil".format(interface))

            local_fault_after = self.get_mac_fault_count(dut, interface, "mac local fault")
            logging.info("MAC local fault count after disabling/enabling rx-output using sfputil {}: {}".format(
                interface, local_fault_after))

            pytest_assert(local_fault_after > local_fault_before,
                          "MAC local fault count did not increment after disabling/enabling tx-output on the device")

    def test_mac_remote_fault_increment(self, select_random_interfaces):
        dut, interfaces = select_random_interfaces

        for interface in interfaces:
            pytest_assert(self.get_interface_status(dut, interface) == "up",
                          "Interface {} was not up before disabling/enabling tx-output using sfputil".format(interface))

            remote_fault_before = self.get_mac_fault_count(dut, interface, "mac remote fault")
            logging.info("Initial MAC remote fault count on {}: {}".format(interface, remote_fault_before))

            dut.shell("sudo sfputil debug tx-output {} disable".format(interface))
            time.sleep(5)
            pytest_assert(self.get_interface_status(dut, interface) == "down",
                          "Interface {} did not go down after disabling rx-output using sfputil".format(interface))

            dut.shell("sudo sfputil debug tx-output {} enable".format(interface))
            time.sleep(20)

            pytest_assert(self.get_interface_status(dut, interface) == "up",
                          "Interface {} did not come up after disabling tx-output using sfputil".format(interface))

            remote_fault_after = self.get_mac_fault_count(dut, interface, "mac remote fault")
            logging.info("MAC remote fault count after disabling/enabling rx-output using sfputil {}: {}".format(
                interface, remote_fault_after))

            pytest_assert(remote_fault_after > remote_fault_before,
                          "MAC remote fault count did not increment after disabling/enabling tx-output on the device")
