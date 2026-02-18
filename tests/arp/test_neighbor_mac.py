"""
=============================================================================
Module: test_neighbor_mac
File: test_neighbor_mac.py
=============================================================================

Description:
    This module tests neighbor MAC address handling in SONiC switches using PTF docker.
    It verifies that MAC address updates for neighbors are correctly propagated from
    the kernel ARP table to the Redis ASIC database, ensuring hardware-software
    consistency in neighbor entry management.

Test Intent:
    - testNeighborMac: Validates that when a neighbor's MAC address is changed on
      the PTF host, the new MAC address is correctly learned and stored in both the
      kernel ARP table and the Redis ASIC_DB neighbor entry. Tests with two different
      MAC addresses to verify update functionality.

Topology:
    m1, t1, ptf (T1-lag and PTF topologies requiring Ethernet0 interface)

Fixtures Used:
    - interfaceConfig: Module-scoped fixture that configures Ethernet0 interface,
      removes it from portchannel if needed, adds IP address, and restores config
      after test completion
    - macIndex: Parameterized fixture (0, 1) to select which test MAC to use
    - configureNeighborIpAndPing: Configures neighbor IP/MAC on PTF and pings DUT
    - redisNeighborMac: Retrieves and validates neighbor MAC from Redis ASIC_DB

Dependencies:
    - tests.common.helpers.assertions: pytest_assert for validation
    - tests.common.utilities: wait_until for polling interface status

Notes:
    - Test requires Ethernet0 to be operational (admin and oper up)
    - Interface is temporarily removed from portchannel if it's a member
    - Uses contextlib.contextmanager for cleanup of portchannel membership
    - Pings DUT from PTF to populate ARP entry before verification
    - 2 second delay allows ARP entries to stabilize before validation
=============================================================================
"""

import contextlib
import logging
import pytest
import time

from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('m1', 't1', 'ptf', 'c0')
]


class TestNeighborMac:
    """
        Test handling of neighbor MAC in SONiC switch with PTF docker
    """
    PTF_HOST_IF = "eth0"
    DUT_ETH_IF = "Ethernet0"
    PTF_HOST_IP = "20.0.0.2"
    PTF_HOST_NETMASK = "255.255.255.0"
    DUT_INTF_IP = "20.0.0.1"
    DUT_INTF_NETMASK = "24"
    TEST_MAC = ["00:c0:ca:c0:1a:05", "00:c0:ca:c0:1a:06"]

    @pytest.fixture(scope="module", autouse=True)
    def interfaceConfig(self, duthosts, rand_one_dut_hostname):
        """
            Configures and Restores DUT configuration after test completes

            Args:
                duthost (AnsibleHost): Device Under Test (DUT)

            Returns:
                None
        """
        duthost = duthosts[rand_one_dut_hostname]

        intfStatus = duthost.show_interface(command="status")["ansible_facts"]["int_status"]
        if self.DUT_ETH_IF not in intfStatus:
            pytest.skip('{} not found'.format(self.DUT_ETH_IF))

        status = intfStatus[self.DUT_ETH_IF]
        if "up" not in status["oper_state"]:
            pytest.skip('{} is down'.format(self.DUT_ETH_IF))

        portchannel = status["vlan"] if "PortChannel" in status["vlan"] else None

        @contextlib.contextmanager
        def removeFromPortChannel(duthost, portchannel, intf):
            try:
                if portchannel:
                    duthost.command("sudo config portchannel member del {} {}".format(portchannel, intf))
                    pytest_assert(wait_until(
                        10, 1, 0,
                        lambda: 'routed' in duthost.show_interface(command="status")
                        ["ansible_facts"]["int_status"][intf]["vlan"]),
                        '{} is not in routed status'.format(intf)
                    )
                yield
            finally:
                if portchannel:
                    duthost.command("sudo config portchannel member add {} {}".format(portchannel, intf))

        with removeFromPortChannel(duthost, portchannel, self.DUT_ETH_IF):
            logger.info("Configure the DUT interface, start interface, add IP address")
            self.__startInterface(duthost)
            self.__configureInterfaceIp(duthost, action="add")

            yield

            logger.info("Restore the DUT interface config, remove IP address")
            self.__configureInterfaceIp(duthost, action="remove")
            self.__shutdownInterface(duthost)

    @pytest.fixture(params=[0, 1])
    def macIndex(self, request):
        """
            Parameterized fixture for macIndex

            Args:
                request: pytest request object

            Returns:
                macIndex (int): index of the mac address used from TEST_MAC
        """
        yield request.param

    def __configureNeighborIp(self, ptfhost, macIndex):
        """
            Configure interface and set IP address/mac address on the PTF host

            Args:
                ptfhost (PTF host): PTF instance used
                macIndex (int): test MAC index to be used

            Returns:
                None
        """
        ptfhost.shell("ifconfig {} {} netmask 255.255.255.0".format(self.PTF_HOST_IF, self.PTF_HOST_IP))
        neighborMac = self.TEST_MAC[macIndex]
        logger.info("neighbor {0} lladdr {1} for {2}".format(self.PTF_HOST_IP, neighborMac, self.PTF_HOST_IF))
        ptfhost.shell("ifconfig {} down".format(self.PTF_HOST_IF))
        ptfhost.shell("ifconfig {} hw ether {}".format(self.PTF_HOST_IF, neighborMac))
        ptfhost.shell("ifconfig {} up".format(self.PTF_HOST_IF))

    def __startInterface(self, duthost):
        """
            Startup the interface on the DUT

            Args:
                duthost (AnsibleHost): Device Under Test (DUT)

            Returns:
                None
        """
        logger.info("Configure the interface '{0}' as UP".format(self.DUT_ETH_IF))
        duthost.shell(argv=[
            "config",
            "interface",
            "startup",
            self.DUT_ETH_IF
        ])

    def __shutdownInterface(self, duthost):
        """
            Shutdown the interface on the DUT

            Args:
                duthost (AnsibleHost): Device Under Test (DUT)

            Returns:
                None
        """
        logger.info("Configure the interface '{0}' as DOWN".format(self.DUT_ETH_IF))
        duthost.shell(argv=[
            "config",
            "interface",
            "shutdown",
            self.DUT_ETH_IF
        ])

    def __configureInterfaceIp(self, duthost, action=None):
        """
            Configure interface IP address on the DUT

            Args:
                duthost (AnsibleHost): Device Under Test (DUT)
                action (str): action to perform, add/remove interface IP

            Returns:
                None
        """

        logger.info("{0} an ip entry {1} for {2}".format(action, self.DUT_INTF_IP, self.DUT_ETH_IF))
        interfaceIp = "{}/{}".format(self.DUT_INTF_IP, self.DUT_INTF_NETMASK)
        duthost.shell(argv=[
            "config",
            "interface",
            "ip",
            action,
            self.DUT_ETH_IF,
            interfaceIp
        ])

    @pytest.fixture(autouse=True)
    def configureNeighborIpAndPing(self, ptfhost, macIndex):
        """
            Configure Neighbor/Interface IP

            Prepares the DUT for testing by adding IP to the test interface, add and update
            the neighbor MAC 2 times.

            Args:
                duthost (AnsibleHost): Device Under Test (DUT)
                ptfhost (PTFHost): PTF instance used
                macIndex (Fixture<int>): Index in the TEST_MAC list

            Returns:
                None
        """
        self.__configureNeighborIp(ptfhost, macIndex)
        ptfhost.shell("ping {} -c 3 -I {}".format(self.DUT_INTF_IP, self.PTF_HOST_IP))

        time.sleep(2)

        yield

    @pytest.fixture
    def redisNeighborMac(self, duthosts, rand_one_dut_hostname, ptfhost, macIndex, configureNeighborIpAndPing):
        """
            Retrieve DUT Redis MAC entry of neighbor IP

            Args:
                duthost (AnsibleHost): Device Under Test (DUT)
                ptfhost (PTFHost): PTF instance used
                macIndex (Fixture<int>): Index in the TEST_MAC list
                configureNeighborIpAndPing (Fixture<str>): test fixture that assign/update IP/neighbor MAC and ping DUT

            Returns:
                redisNeighborMac (str): Redis MAC entry of neighbor IP
        """
        duthost = duthosts[rand_one_dut_hostname]
        result = duthost.shell(argv=["redis-cli", "-n", "1", "KEYS", "ASIC_STATE:SAI_OBJECT_TYPE_NEIGHBOR_ENTRY*"])
        neighborKey = None
        for key in result["stdout_lines"]:
            if self.PTF_HOST_IP in key:
                neighborKey = key
                break

        pytest_assert(neighborKey, "Neighbor key NOT found in Redis DB, Redis db Output '{0}'".format(result["stdout"]))
        result = duthost.shell(argv=["redis-cli", "-n", "1", "HGETALL", neighborKey])

        yield result["stdout_lines"][1]

    def testNeighborMac(self, macIndex, redisNeighborMac):
        """
            Neighbor MAC test

            Args:
                macIndex (Fixture<int>): Index in the TEST_MAC list
                redisNeighborMac (Fixture<str>): Redis MAC entry of neighbor IP

            Returns:
                None
        """
        testMac = self.TEST_MAC[macIndex]
        pytest_assert(
            redisNeighborMac.lower() == testMac,
            "Failed to find test MAC address '{0}' in Redis Neighbor table '{1}'".format(testMac, redisNeighborMac)
        )
