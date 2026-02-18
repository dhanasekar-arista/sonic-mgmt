"""
=============================================================================
Module: macsec
File: test_fault_handling.py
=============================================================================

Description:
    This test validates MACsec fault handling and resilience under various
    link failure scenarios. It tests MKA session recovery after different
    durations of link flaps and validates detection of MACsec configuration
    mismatches between peers.

Test Intent:
    - test_link_flap: Tests MACsec resilience under three link flap scenarios:
      1) Short flap (<6s MKA timeout): Verifies SA tables remain unchanged,
         MKA session not re-established (SONiC neighbors only, not EOS)
      2) Medium flap (>6s but <90s LACP timeout): Verifies new MKA session
         established with different SA tables within 30 seconds
      3) Long flap (>90s): Verifies portchannel goes down, then recovers
         when link is restored. Tests LACP interaction with MACsec.
      Includes retry logic for rekey race conditions.
    - test_mismatch_macsec_configuration: Validates that MACsec session does
      NOT establish when peers have mismatched CAK (Connectivity Association
      Key). Disables MACsec on both ends, configures neighbor with wrong CAK
      (all zeros), enables both sides, and verifies MKA establishment fails
      within 90 seconds. Ensures security by preventing sessions with
      incorrect credentials. Performs cleanup in teardown.

Topology:
    t0, t2, t0-sonic topologies with MACsec support required

Fixtures Used:
    - duthost: DUT host object for test execution
    - ctrl_links: Dictionary of MACsec-controlled links on the DUT
    - unctrl_links: Dictionary of uncontrolled (non-MACsec) links for testing
    - wait_mka_establish: Waits for MKA session establishment before tests
    - profile_name: MACsec profile name
    - default_priority: MACsec profile priority
    - cipher_suite: MACsec cipher suite
    - primary_cak, primary_ckn: CAK and CKN for MKA
    - policy: MACsec policy configuration
    - send_sci: Whether to send SCI in MACsec frames

Dependencies:
    - tests.common.utilities: For wait_until polling functionality
    - tests.common.devices.eos: For EOS device support
    - tests.common.macsec.macsec_helper: For APPL_DB retrieval
    - tests.common.macsec.macsec_config_helper: For MACsec port and profile
      configuration
    - tests.common.macsec.macsec_platform_helper: For interface and
      portchannel operations

Notes:
    - Both tests disable loganalyzer
    - MKA_TIMEOUT = 6 seconds
    - LACP_TIMEOUT = 90 seconds
    - test_link_flap picks first controlled link for testing
    - Short flap test not supported on EOS neighbors (SONiC only)
    - Short flap test has 3 retries with 30s idle time to avoid rekey races
    - Medium flap waits up to 30 seconds for new MKA session
    - Long flap waits up to 12 seconds for portchannel status changes
    - test_mismatch_macsec_configuration skips if no uncontrolled links
    - test_mismatch_macsec_configuration uses all-zero CAK as wrong credential
    - Mismatch test waits 20 seconds for session teardown before config change
    - Mismatch test verifies NO MKA establishment within 90 seconds
    - Mismatch test sleeps 300 seconds during teardown for cleanup
    - Supports both SONiC and EOS neighbors
=============================================================================
"""
from time import sleep
import pytest
import logging

from tests.common.utilities import wait_until
from tests.common.devices.eos import EosHost
from tests.common.macsec.macsec_helper import get_appl_db
from tests.common.macsec.macsec_config_helper import disable_macsec_port, \
    enable_macsec_port, delete_macsec_profile, set_macsec_profile
from tests.common.macsec.macsec_platform_helper import get_eth_ifname, find_portchannel_from_member, get_portchannel

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.macsec_required,
    pytest.mark.topology("t0", "t2", "t0-sonic"),
]


class TestFaultHandling():
    MKA_TIMEOUT = 6
    LACP_TIMEOUT = 90

    @pytest.mark.disable_loganalyzer
    def test_link_flap(self, duthost, ctrl_links, wait_mka_establish):
        # Only pick one link for link flap test
        assert ctrl_links, (
            "No control links found. Expected at least one control link, but got {}.\n"
            "Actual ctrl_links: {}"
        ).format(len(ctrl_links), ctrl_links)

        port_name, nbr = list(ctrl_links.items())[0]
        nbr_eth_port = get_eth_ifname(
            nbr["host"], nbr["port"])
        _, _, _, dut_egress_sa_table_orig, dut_ingress_sa_table_orig = get_appl_db(
            duthost, port_name, nbr["host"], nbr["port"])

        # Flap < 6 seconds
        # Not working on eos neighbour
        if not isinstance(nbr["host"], EosHost):
            # Rekey may happen during the following assertions, so we need to get the SA tables again
            retry = 3
            while retry > 0:
                retry -= 1
                try:
                    nbr["host"].shell("config interface shutdown {}  && sleep 1 && config interface startup {}".format(
                        nbr["port"], nbr["port"]))
                    _, _, _, dut_egress_sa_table_new, dut_ingress_sa_table_new = get_appl_db(
                        duthost, port_name, nbr["host"], nbr["port"])
                    assert dut_egress_sa_table_orig == dut_egress_sa_table_new, (
                        "DUT egress SA table mismatch. Original table: {}, New table: {}. "
                    ).format(dut_egress_sa_table_orig, dut_egress_sa_table_new)

                    assert dut_ingress_sa_table_orig == dut_ingress_sa_table_new, (
                        "DUT ingress SA table mismatch. Original table: {}, New table: {}. "
                    ).format(dut_ingress_sa_table_orig, dut_ingress_sa_table_new)
                    break
                except AssertionError as e:
                    if retry == 0:
                        raise e
                    # This test may fail due to the lag of DUT exceeding MKA_TIMEOUT that triggers a rekey.
                    # To mitigate this, retry the test after a while with a few seconds of idle time.
                    sleep(30)
                dut_egress_sa_table_orig, dut_ingress_sa_table_orig = dut_egress_sa_table_new, dut_ingress_sa_table_new

        # Flap > 6 seconds but < 90 seconds
        if isinstance(nbr["host"], EosHost):
            nbr["host"].shutdown(nbr_eth_port)
            sleep(TestFaultHandling.MKA_TIMEOUT)
            nbr["host"].no_shutdown(nbr_eth_port)
        else:
            nbr["host"].shell("config interface shutdown {}  && sleep {} && config interface startup {}".format(
                nbr["port"], TestFaultHandling.MKA_TIMEOUT, nbr["port"]))

        def check_new_mka_session():
            _, _, _, dut_egress_sa_table_new, dut_ingress_sa_table_new = get_appl_db(
                duthost, port_name, nbr["host"], nbr["port"])
            assert dut_egress_sa_table_new, (
                "DUT egress SA table is empty. Expected non-empty table, but got {}. "
            ).format(dut_egress_sa_table_new)
            assert dut_ingress_sa_table_new, (
                "DUT ingress SA table is empty. Expected non-empty table, but got {}. "
            ).format(dut_ingress_sa_table_new)
            assert dut_egress_sa_table_orig != dut_egress_sa_table_new, (
                "DUT egress SA table remains the same. Original table: {}, New table: {}. "
                "Expected tables to be different, but they are identical. "
            ).format(dut_egress_sa_table_orig, dut_egress_sa_table_new)
            assert dut_ingress_sa_table_orig != dut_ingress_sa_table_new, (
                "DUT ingress SA table remains the same. Original table: {}, New table: {}. "
                "Expected tables to be different, but they are identical. "
            ).format(dut_ingress_sa_table_orig, dut_ingress_sa_table_new)
            return True
        assert wait_until(30, 5, 2, check_new_mka_session), (
            "New MKA session not established within expected time. ")

        # Flap > 90 seconds
        assert wait_until(12, 1, 0, lambda: find_portchannel_from_member(
            port_name, get_portchannel(duthost))["status"] == "Up"), (
            "Portchannel {} did not come up within expected time. "
            "Portchannel status: {} "
            "Find portchannel from member: {} "
        ).format(
            port_name,
            find_portchannel_from_member(port_name, get_portchannel(duthost))["status"],
            find_portchannel_from_member(port_name, get_portchannel(duthost))
        )

        if isinstance(nbr["host"], EosHost):
            nbr["host"].shutdown(nbr_eth_port)
            sleep(TestFaultHandling.LACP_TIMEOUT)
        else:
            nbr["host"].shell("ifconfig {} down && sleep {}".format(
                nbr_eth_port, TestFaultHandling.LACP_TIMEOUT))
        assert wait_until(6, 1, 0, lambda: find_portchannel_from_member(
                    port_name, get_portchannel(duthost))["status"] == "Dw"), (
            "Portchannel {} did not go down within expected time. "
            "Portchannel status: {} "
            "Find portchannel from member: {} "
        ).format(
            port_name,
            find_portchannel_from_member(port_name, get_portchannel(duthost))["status"],
            find_portchannel_from_member(port_name, get_portchannel(duthost))
        )

        if isinstance(nbr["host"], EosHost):
            nbr["host"].no_shutdown(nbr_eth_port)
        else:
            nbr["host"].shell("ifconfig {} up".format(nbr_eth_port))
        assert wait_until(12, 1, 0, lambda: find_portchannel_from_member(
            port_name, get_portchannel(duthost))["status"] == "Up"), (
            "Portchannel {} did not come up within expected time. "
            "Portchannel status: {} "
            "Find portchannel from member: {} "
        ).format(
            port_name,
            find_portchannel_from_member(port_name, get_portchannel(duthost))["status"],
            find_portchannel_from_member(port_name, get_portchannel(duthost))
        )

    @pytest.mark.disable_loganalyzer
    def test_mismatch_macsec_configuration(self, duthost, unctrl_links,
                                           profile_name, default_priority, cipher_suite,
                                           primary_cak, primary_ckn, policy, send_sci, wait_mka_establish):
        # Only pick one uncontrolled link for mismatch macsec configuration test
        if not unctrl_links:
            pytest.skip('SKIP this test as there are no uncontrolled links in this dut')

        port_name, nbr = list(unctrl_links.items())[0]

        disable_macsec_port(duthost, port_name)
        disable_macsec_port(nbr["host"], nbr["port"])
        delete_macsec_profile(nbr["host"], nbr["port"], profile_name)

        # Wait till macsec session has gone down.
        wait_until(20, 3, 0,
                   lambda: not duthost.iface_macsec_ok(port_name) and
                   not nbr["host"].iface_macsec_ok(nbr["port"]))

        # Set a wrong cak to the profile
        primary_cak = "0" * len(primary_cak)
        enable_macsec_port(duthost, port_name, profile_name)
        set_macsec_profile(nbr["host"], nbr["port"], profile_name, default_priority,
                           cipher_suite, primary_cak, primary_ckn, policy, send_sci)
        enable_macsec_port(nbr["host"], nbr["port"], profile_name)

        def check_mka_establishment():
            _, _, dut_ingress_sc_table, dut_egress_sa_table, dut_ingress_sa_table = get_appl_db(
                duthost, port_name, nbr["host"], nbr["port"])
            return dut_ingress_sc_table or dut_egress_sa_table or dut_ingress_sa_table
        # The mka should be establishing or established
        # To check whether the MKA establishment happened within 90 seconds
        assert not wait_until(90, 1, 12, check_mka_establishment), (
            "MKA establishment failed. Expected MKA to not establish within expected time, but it did. "
        )

        # Teardown
        disable_macsec_port(duthost, port_name)
        disable_macsec_port(nbr["host"], nbr["port"])
        delete_macsec_profile(nbr["host"], nbr["port"], profile_name)
        sleep(300)
