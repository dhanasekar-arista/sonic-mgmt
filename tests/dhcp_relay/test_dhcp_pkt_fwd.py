"""
Module: tests.dhcp_relay.test_dhcp_pkt_fwd
File: test_dhcp_pkt_fwd.py

Description:
    DHCP packet forwarding validation test suite for T1 topology. This module verifies that DHCP
    packets (Discover, Offer, Request, Ack) are correctly forwarded through T1 devices between
    downstream (T0/MX) and upstream (T2/M1) neighbors. Tests validate proper L2 and L3 packet
    transformations during forwarding, including MAC address rewriting and TTL decrementation.

Test Intent:
    - Verify DHCP Discover packets are forwarded from downstream to upstream ports
    - Validate DHCP Offer packets are forwarded from upstream to downstream ports
    - Test DHCP Request packets are forwarded from downstream to upstream ports
    - Verify DHCP Ack packets are forwarded from upstream to downstream ports
    - Validate proper MAC address rewriting (src set to router_mac, dst updated)
    - Test TTL decrementation during L3 forwarding
    - Verify DHCP relay agent information (giaddr) is preserved
    - Validate packet forwarding through LAG member ports
    - Test static route creation for DHCP server and relay IP reachability

Topology:
    - t1: T1 topology with T0 (downstream) and T2 (upstream) neighbors
    - m0: Management topology with MX (downstream) and M1 (upstream) neighbors
    - m1: Management M1 topology
    T1 device acts as DHCP relay forwarding packets between T0/T2 or MX/M1

Fixtures Used:
    - dutPorts: Dictionary of upstream and downstream ports on DUT
    - testPorts: Selected test ports (LAG members) for upstream and downstream
    - duthosts, rand_one_dut_hostname: DUT host selection
    - tbinfo: Testbed information including topology type
    - ptfadapter: PTF adapter for packet transmission and verification

Dependencies:
    - PTF framework for packet generation and verification
    - BGP configuration with T0/T2 or MX/M1 neighbors
    - Static routes to DHCP server and relay IPs via BGP peers
    - PortChannel (LAG) support for multi-member link aggregation
    - Minigraph facts for port/neighbor information

Notes:
    - Tests run on T1 and M0 topologies only (skipped on other topologies)
    - DHCP client MAC: 00:11:22:33:44:55, IP: 10.10.10.1
    - DHCP relay MAC: 22:33:44:55:00:11, IP: 20.20.20.1, Loopback: 10.0.0.33
    - DHCP server MAC: 44:55:00:11:22:33, IP: 30.30.30.30
    - DHCP client port: 68, server port: 67
    - DHCP lease time: 86400 seconds (1 day)
    - Minimum BOOTP packet length: 300 bytes (padded if needed)
    - Broadcast bit set (0x8000) in BOOTP flags
    - GIADDR set to relay IP in relayed packets
    - Static routes added/removed via vtysh during test setup/teardown
    - Packet forwarding validated using PTF Mask for flexible field matching
    - Tests use scapy for DHCP packet construction and parsing

Git History (last 10 commits):
    ca9f91a1d [topo] Clear m2 m3 topo
    d537254a4 [M1/M2/M3] Add pytest mark for M1/M2/M3 topo
    dab77c420 Remove TACACS fixture from none TACACS test cases
    07f328770 Enable TACACS on test cases
    b238474d1 [dhcp_relay][m0] Add support for in test_dhcp_pkt_fwd for m0-2vlan
    efb25e571 [Python3 migration]sonic-mgmt repo first batch Python3 migration
    f7fd5b7e7 Revert "sonic-mgmt repo Python2 to Python3 migration (#7697)"
    97c89590d sonic-mgmt repo Python2 to Python3 migration
    3e8c217c8 [pre-commit] Fix style issues in test scripts under tests/decap, tests/dhcp_relay, tests/disk folder
    5990a1885 [m0] Add support for m0 in test_dhcp_pkt_fwd
"""

import logging
import random
import ipaddr
import pytest
import ipaddress

import ptf.testutils as testutils
import ptf.packet as scapy

from ptf.mask import Mask
from socket import INADDR_ANY

pytestmark = [
    pytest.mark.topology("t1", "m0", "m1")
]

logger = logging.getLogger(__name__)


class DhcpPktFwdBase:
    """Base class for DHCP packet forwarding test. The test ensure that DHCP packets are going through T1 device."""
    LEASE_TIME_SEC = 86400
    DHCP_PKT_BOOTP_MIN_LEN = 300
    DHCP_CLIENT = {
        "mac": "00:11:22:33:44:55",
        "ip": "10.10.10.1",
        "subnet": "255.255.255.0",
        "port": 68,
    }
    DHCP_RELAY = {
        "mac": "22:33:44:55:00:11",
        "ip": "20.20.20.1",
        "loopback": "10.0.0.33",
    }
    DHCP_SERVER = {
        "mac": "44:55:00:11:22:33",
        "ip": "30.30.30.30",
        "port": 67,
    }

    def __getPortLagsAndPeerIp(self, duthost, testPort, tbinfo):
        """
        Retrieves all port lag members for a given testPort

        Args:
            duthost(Ansible Fixture): instance of SonicHost class of DUT
            testPort(str): port name used for test

        Returns:
            lags(list): list of port indices (if any) if LAG which has testPort as a member
            peerIp(str): BGP peer IP
        """
        peerIp = None
        mgFacts = duthost.get_extended_minigraph_facts(tbinfo)
        for peer in mgFacts["minigraph_bgp"]:
            if peer["name"] == mgFacts["minigraph_neighbors"][testPort]["name"] and \
               ipaddr.IPAddress(peer["addr"]).version == 4:
                peerIp = peer["addr"]
                break

        lags = [mgFacts["minigraph_ptf_indices"][testPort]]
        for portchannelConfig in list(mgFacts["minigraph_portchannels"].values()):
            if testPort in portchannelConfig["members"]:
                for lag in portchannelConfig["members"]:
                    if testPort != lag:
                        lags.append(mgFacts["minigraph_ptf_indices"][lag])
                break

        return lags, peerIp

    def __updateRoute(self, duthost, ip, peerIp, op=""):
        """
        Update route to add/remove for a given IP <ip> towards BGP peer

         Args:
            duthost(Ansible Fixture): instance of SonicHost class of DUT
            ip(str): IP to add/remove route for
            peerIp(str): BGP peer IP
            op(str): operation add/remove to be performed, default add

        Returns:
            None
        """
        logger.info("{0} route to '{1}' via '{2}'".format(
            "Deleting" if "no" == op else "Adding",
            ip,
            peerIp
        ))
        duthost.shell("vtysh -c \"configure terminal\" -c \"{} ip route {} {}\"".format(
            op,
            ipaddress.ip_interface((ip + "/24").encode().decode("utf-8")).network,
            peerIp
        ))

    @pytest.fixture(scope="class")
    def dutPorts(self, duthosts, rand_one_dut_hostname, tbinfo):
        """
        Build list of DUT ports and classify them as Upstream/Downstream ports.

        Args:
            duthost(Ansible Fixture): instance of SonicHost class of DUT
            tbinfo(Ansible Fixture): testbed information

        Returns:
            dict: contains downstream/upstream ports information
        """
        duthost = duthosts[rand_one_dut_hostname]
        topo_name = tbinfo["topo"]["name"]
        if "t1" not in topo_name and tbinfo["topo"]["type"] != "m0":
            pytest.skip("Unsupported topology: {}".format(topo_name))

        downstreamPorts = []
        upstreamPorts = []

        mgFacts = duthost.get_extended_minigraph_facts(tbinfo)

        for dutPort, neigh in list(mgFacts["minigraph_neighbors"].items()):
            if "t1" in topo_name and "T0" in neigh["name"] or "m0" in topo_name and "MX" in neigh["name"]:
                downstreamPorts.append(dutPort)
            elif "t1" in topo_name and "T2" in neigh["name"] or "m0" in topo_name and "M1" in neigh["name"]:
                upstreamPorts.append(dutPort)

        yield {"upstreamPorts": upstreamPorts, "downstreamPorts": downstreamPorts}

    @pytest.fixture(scope="class")
    def testPorts(self, duthosts, rand_one_dut_hostname, dutPorts, tbinfo):
        """
        Select one upstream and one downstream ports for DHCP packet forwarding test

        Args:
            duthost(Ansible Fixture): instance of SonicHost class of DUT
            dutPorts(Ansible Fixture, dict): contains downstream/upstream ports information

        Returns:
            dict: contains downstream/upstream port (or LAG members) information used for test
        """
        duthost = duthosts[rand_one_dut_hostname]
        downstreamLags, downstreamPeerIp = self.__getPortLagsAndPeerIp(
            duthost,
            random.choice(dutPorts["downstreamPorts"]),
            tbinfo
        )
        upstreamLags, upstreamPeerIp = self.__getPortLagsAndPeerIp(
            duthost,
            random.choice(dutPorts["upstreamPorts"]),
            tbinfo
        )

        duthost.update_ip_route(self.DHCP_SERVER["ip"], upstreamPeerIp)
        duthost.update_ip_route(self.DHCP_RELAY["ip"], downstreamPeerIp)

        yield {"upstream": upstreamLags, "downstream": downstreamLags}

        duthost.update_ip_route(self.DHCP_SERVER["ip"], upstreamPeerIp, "no")
        duthost.update_ip_route(self.DHCP_RELAY["ip"], downstreamPeerIp, "no")

    @classmethod
    def createDhcpDiscoverRelayedPacket(self, dutMac):
        """
        Helper function that creates DHCP Discover packet destined to DUT

        Args:
            dutMac(str): MAC address of DUT

        Returns:
            packet: DHCP Discover packet
        """
        ether = scapy.Ether(dst=dutMac, src=self.DHCP_RELAY["mac"], type=0x0800)
        ip = scapy.IP(src=self.DHCP_RELAY["loopback"], dst=self.DHCP_SERVER["ip"], len=328, ttl=64)
        udp = scapy.UDP(sport=self.DHCP_SERVER["port"], dport=self.DHCP_SERVER["port"], len=308)
        bootp = scapy.BOOTP(
            op=1,
            htype=1,
            hlen=6,
            hops=1,
            xid=0,
            secs=0,
            flags=0x8000,
            ciaddr=str(INADDR_ANY),
            yiaddr=str(INADDR_ANY),
            siaddr=str(INADDR_ANY),
            giaddr=self.DHCP_RELAY["ip"],
            chaddr=''.join([chr(int(octet, 16)) for octet in self.DHCP_CLIENT["mac"].split(':')])
        )
        bootp /= scapy.DHCP(options=[
            ("message-type", "discover"),
            ("end")
        ])

        pad_bytes = self.DHCP_PKT_BOOTP_MIN_LEN - len(bootp)
        if pad_bytes > 0:
            bootp /= scapy.PADDING("\x00" * pad_bytes)

        pkt = ether / ip / udp / bootp

        return pkt

    @classmethod
    def createDhcpOfferPacket(self, dutMac):
        """
        Helper function that creates DHCP Offer packet destined to DUT

        Args:
            dutMac(str): MAC address of DUT

        Returns:
            packet: DHCP Offer packet
        """
        return testutils.dhcp_offer_packet(
            eth_dst=dutMac,
            eth_server=self.DHCP_RELAY["mac"],
            eth_client=self.DHCP_CLIENT["mac"],
            ip_server=self.DHCP_SERVER["ip"],
            ip_dst=self.DHCP_RELAY["ip"],
            ip_offered=self.DHCP_CLIENT["ip"],
            port_dst=self.DHCP_SERVER["port"],
            ip_gateway=self.DHCP_RELAY["ip"],
            netmask_client=self.DHCP_CLIENT["subnet"],
            dhcp_lease=self.LEASE_TIME_SEC,
            padding_bytes=0,
            set_broadcast_bit=True
        )

    @classmethod
    def createDhcpRequestRelayedPacket(self, dutMac):
        """
        Helper function that creates DHCP Request packet destined to DUT

        Args:
            dutMac(str): MAC address of DUT

        Returns:
            packet: DHCP Request packet
        """
        ether = scapy.Ether(dst=dutMac, src=self.DHCP_RELAY["mac"], type=0x0800)
        ip = scapy.IP(src=self.DHCP_RELAY["loopback"], dst=self.DHCP_SERVER["ip"], len=328, ttl=64)
        udp = scapy.UDP(sport=self.DHCP_SERVER["port"], dport=self.DHCP_SERVER["port"], len=308)
        bootp = scapy.BOOTP(
            op=1,
            htype=1,
            hlen=6,
            hops=1,
            xid=0,
            secs=0,
            flags=0x8000,
            ciaddr=str(INADDR_ANY),
            yiaddr=str(INADDR_ANY),
            siaddr=str(INADDR_ANY),
            giaddr=self.DHCP_RELAY["ip"],
            chaddr=''.join([chr(int(octet, 16)) for octet in self.DHCP_CLIENT["mac"].split(':')])
        )
        bootp /= scapy.DHCP(options=[
            ("message-type", "request"),
            ("requested_addr", self.DHCP_CLIENT["ip"]),
            ("server_id", self.DHCP_SERVER["ip"]),
            ("end")
        ])

        pad_bytes = self.DHCP_PKT_BOOTP_MIN_LEN - len(bootp)
        if pad_bytes > 0:
            bootp /= scapy.PADDING("\x00" * pad_bytes)

        pkt = ether / ip / udp / bootp

        return pkt

    @classmethod
    def createDhcpAckPacket(self, dutMac):
        """
        Helper function that creates DHCP Discover ACK destined to DUT

        Args:
            dutMac(str): MAC address of DUT

        Returns:
            packet: DHCP ACK packet
        """
        return testutils.dhcp_ack_packet(
            eth_dst=dutMac,
            eth_server=self.DHCP_RELAY["mac"],
            eth_client=self.DHCP_CLIENT["mac"],
            ip_server=self.DHCP_SERVER["ip"],
            ip_dst=self.DHCP_RELAY["ip"],
            ip_offered=self.DHCP_CLIENT["ip"],
            port_dst=self.DHCP_SERVER["port"],
            ip_gateway=self.DHCP_RELAY["ip"],
            netmask_client=self.DHCP_CLIENT["subnet"],
            dhcp_lease=self.LEASE_TIME_SEC,
            padding_bytes=0,
            set_broadcast_bit=True
        )


class TestDhcpPktFwd(DhcpPktFwdBase):
    """DHCP Packet forward test class"""
    @pytest.mark.parametrize("pktInfo", [
        {"txDir": "downstream", "rxDir": "upstream", "pktGen": DhcpPktFwdBase.createDhcpDiscoverRelayedPacket},
        {"txDir": "upstream", "rxDir": "downstream", "pktGen": DhcpPktFwdBase.createDhcpOfferPacket},
        {"txDir": "downstream", "rxDir": "upstream", "pktGen": DhcpPktFwdBase.createDhcpRequestRelayedPacket},
        {"txDir": "upstream", "rxDir": "downstream", "pktGen": DhcpPktFwdBase.createDhcpAckPacket},
    ])
    def testDhcpPacketForwarding(self, duthost, testPorts, ptfadapter, pktInfo):
        """
        Validates that DHCP Discover/Offer/Request/Ack (DORA) packets are forwarded through T1 devices

         Args:
            duthost(Ansible Fixture): instance of SonicHost class of DUT
            testPorts(Ansible Fixture, dict): contains downstream/upstream test ports information
            ptfadapter(Ansible Fixture): instance of PTF Adapter
            pktInfo(Pytest Params<dict>): test parameters containing information on which ports used for
                                          sending/receiving DHCP packet and
                                          DHCP packet to send
        """
        ptfadapter.dataplane.flush()

        dhcpPacket = pktInfo["pktGen"](duthost.facts["router_mac"])
        testutils.send(ptfadapter, random.choice(testPorts[pktInfo["txDir"]]), dhcpPacket)

        # Update fields of the forwarded packet
        dhcpPacket[scapy.Ether].src = duthost.facts["router_mac"]
        dhcpPacket[scapy.IP].ttl = dhcpPacket[scapy.IP].ttl - duthost.ttl_decr_value

        expectedDhcpPacket = Mask(dhcpPacket)
        expectedDhcpPacket.set_do_not_care_scapy(scapy.Ether, "dst")
        expectedDhcpPacket.set_do_not_care_scapy(scapy.IP, "chksum")

        _, receivedPacket = testutils.verify_packet_any_port(
            ptfadapter,
            expectedDhcpPacket,
            ports=testPorts[pktInfo["rxDir"]]
        )
        logger.info("Received packet: %s", scapy.Ether(receivedPacket).summary())
