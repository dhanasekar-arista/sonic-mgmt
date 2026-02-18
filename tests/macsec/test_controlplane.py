"""
=============================================================================
Module: macsec
File: test_controlplane.py
=============================================================================

Description:
    This test validates MACsec (Media Access Control Security) control plane
    functionality on SONiC devices. It verifies MKA (MACsec Key Agreement)
    session establishment, APPL_DB state, WPA supplicant processes, rekey
    operations, and profile replacement scenarios for encrypted links.

Test Intent:
    - test_wpa_supplicant_processes: Validates that WPA supplicant processes
      are running on both DUT and neighbor devices for all MACsec-controlled
      links. Ensures MACsec authentication infrastructure is operational.
    - test_appl_db: Verifies MACsec configuration in APPL_DB matches expected
      policy, cipher suite, and SCI settings for all controlled links.
    - test_mka_session: Validates MKA session establishment between DUT and
      neighbors. Checks SCI (Secure Channel Identifier), cipher suite, policy,
      and send_sci configuration match on both ends. Skips detailed MKA checks
      on physical switches (non-KVM).
    - test_rekey_by_period: Tests automatic MACsec key rotation based on rekey
      period. Verifies SA (Security Association) tables change after rekey
      while maintaining traffic continuity (less than 1% packet loss during
      rekey). Skips if rekey_period is 0.
    - test_profile_replace: Validates dynamic MACsec profile replacement.
      Ensures new MKA session is established with new profile within 60 seconds
      and SA tables are updated. Reverts to original profile after test.

Topology:
    t0, t2, t0-sonic topologies with MACsec support required

Fixtures Used:
    - duthost: DUT host object for test execution
    - ctrl_links: Dictionary of MACsec-controlled links on the DUT
    - upstream_links: Upstream link information for traffic testing
    - downstream_links: Downstream link information
    - policy: MACsec policy configuration
    - cipher_suite: MACsec cipher suite (e.g., GCM-AES-128, GCM-AES-256)
    - send_sci: Whether to send SCI in MACsec frames
    - wait_mka_establish: Waits for MKA session establishment before tests
    - rekey_period: Period for automatic key rotation
    - profile_name: MACsec profile name
    - primary_cak, primary_ckn: CAK and CKN for MKA
    - default_priority: MACsec profile priority
    - tbinfo: Testbed information

Dependencies:
    - tests.common.utilities: For wait_until polling functionality
    - tests.common.devices.eos: For EOS device support
    - tests.common.macsec.macsec_helper: MACsec validation and data retrieval
    - tests.common.macsec.macsec_config_helper: MACsec configuration management
    - tests.common.macsec.macsec_platform_helper: Platform-specific helpers

Notes:
    - Requires MACsec-capable hardware and topology
    - test_mka_session skips detailed checks on physical switches (non-KVM)
    - test_rekey_by_period uses ping to verify less than 1% packet loss
    - test_profile_replace disables loganalyzer and reverts configuration
    - Waits up to 300 seconds for WPA supplicant, APPL_DB, and MKA session
    - Profile replacement test waits 60 seconds for new MKA session
    - Supports both SONiC and EOS neighbors
=============================================================================
"""
from time import sleep
import pytest
import logging
import re

from tests.common.utilities import wait_until
from tests.common.devices.eos import EosHost
from tests.common.macsec.macsec_helper import check_wpa_supplicant_process, check_appl_db, check_mka_session,\
                           get_mka_session, get_sci, get_appl_db, get_ipnetns_prefix
from tests.common.macsec.macsec_config_helper import setup_macsec_configuration, delete_macsec_profile
from tests.common.macsec.macsec_platform_helper import get_platform, get_macsec_ifname

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.macsec_required,
    pytest.mark.topology("t0", "t2", "t0-sonic"),
]


class TestControlPlane():
    def test_wpa_supplicant_processes(self, duthost, ctrl_links):
        def _test_wpa_supplicant_processes():
            for port_name, nbr in list(ctrl_links.items()):
                check_wpa_supplicant_process(duthost, port_name)
                if isinstance(nbr["host"], EosHost):
                    continue
                check_wpa_supplicant_process(nbr["host"], nbr["port"])
            return True
        assert wait_until(300, 1, 1, _test_wpa_supplicant_processes)

    def test_appl_db(self, duthost, ctrl_links, policy, cipher_suite, send_sci, wait_mka_establish):
        assert wait_until(300, 6, 12, check_appl_db, duthost, ctrl_links, policy, cipher_suite, send_sci)

    def test_mka_session(self, duthost, ctrl_links, policy, cipher_suite, send_sci, wait_mka_establish):
        def _test_mka_session():
            # If the DUT isn't a virtual switch that cannot support "get mka session" by "ip macsec show"
            # So, skip this test for physical switch
            # TODO: Support "get mka session" in the physical switch
            if "x86_64-kvm_x86_64" not in get_platform(duthost):
                # TODO: add check mka session later, now wait some time for session ready
                sleep(30)
                logging.info(
                    "Skip to check mka session due to the DUT isn't a virtual switch")
                return True
            dut_mka_session = get_mka_session(duthost)
            assert len(dut_mka_session) == len(ctrl_links)
            for port_name, nbr in list(ctrl_links.items()):
                if isinstance(nbr["host"], EosHost):
                    assert nbr["host"].iface_macsec_ok(nbr["port"])
                    continue
                nbr_mka_session = get_mka_session(nbr["host"])
                dut_macsec_port = get_macsec_ifname(duthost, port_name)
                nbr_macsec_port = get_macsec_ifname(
                    nbr["host"], nbr["port"])
                dut_macaddress = duthost.get_dut_iface_mac(port_name)
                nbr_macaddress = nbr["host"].get_dut_iface_mac(nbr["port"])
                dut_sci = get_sci(dut_macaddress)
                nbr_sci = get_sci(nbr_macaddress)
                check_mka_session(dut_mka_session[dut_macsec_port], dut_sci,
                                  nbr_mka_session[nbr_macsec_port], nbr_sci,
                                  policy, cipher_suite, send_sci)
            return True
        assert wait_until(300, 5, 3, _test_mka_session)

    def test_rekey_by_period(self, duthost, ctrl_links, upstream_links, rekey_period, wait_mka_establish):
        if rekey_period == 0:
            pytest.skip("If the rekey period is 0 which means rekey by period isn't active.")
        assert len(ctrl_links) > 0
        # Only pick one link to test
        port_name, nbr = list(ctrl_links.items())[0]
        _, _, _, last_dut_egress_sa_table, last_dut_ingress_sa_table = get_appl_db(
            duthost, port_name, nbr["host"], nbr["port"])
        up_link = upstream_links[port_name]
        tmp_file = "/tmp/rekey_ping.txt"
        # This ping commands may take a long time to confirm the packet loss during rekey rotation,
        # But this time may exceed the maximum timeout of SSH so that the Ansible comes to disconnection.
        duthost.shell(
            "bash -c 'sudo nohup {} ping {} -q -w {} -i 0.1 > {} &'".format(get_ipnetns_prefix(duthost, port_name),
                                                                            up_link["local_ipv4_addr"],
                                                                            rekey_period * 2, tmp_file))
        sleep(rekey_period * 2)
        output = duthost.command("cat {}".format(tmp_file))["stdout_lines"]
        _, _, _, new_dut_egress_sa_table, new_dut_ingress_sa_table = get_appl_db(
            duthost, port_name, nbr["host"], nbr["port"])
        assert last_dut_egress_sa_table != new_dut_egress_sa_table
        assert last_dut_ingress_sa_table != new_dut_ingress_sa_table
        assert float(re.search(r"([\d\.]+)% packet loss", output[-2]).group(1)) < 1.0
        duthost.command("rm {}".format(tmp_file))

    @pytest.mark.disable_loganalyzer
    def test_profile_replace(self, duthost, ctrl_links,
                             profile_name, default_priority, cipher_suite,
                             primary_cak, primary_ckn, policy, send_sci, rekey_period, tbinfo, wait_mka_establish):
        # Only pick one controlled link for profile replace test
        ctrl_link = dict([next(iter(ctrl_links.items()))])
        port_name, nbr = list(ctrl_link.items())[0]
        _, _, _, last_dut_egress_sa_table, last_dut_ingress_sa_table = get_appl_db(
            duthost, port_name, nbr["host"], nbr["port"])
        # Replace existing profile with new profile
        new_profile_name = profile_name+"_NEW"
        setup_macsec_configuration(duthost, ctrl_link, new_profile_name, default_priority,
                                   cipher_suite, primary_cak, primary_ckn, policy, send_sci, rekey_period, tbinfo)

        def check_mka_new_session():
            _, _, new_dut_ingress_sc_table, new_dut_egress_sa_table, new_dut_ingress_sa_table = get_appl_db(
                duthost, port_name, nbr["host"], nbr["port"])
            assert new_dut_ingress_sc_table
            assert new_dut_egress_sa_table
            assert new_dut_ingress_sa_table
            assert last_dut_egress_sa_table != new_dut_egress_sa_table
            assert last_dut_ingress_sa_table != new_dut_ingress_sa_table
            return True
        try:
            # To check whether the MKA establishment happened within 60 seconds
            assert wait_until(60, 5, 2, check_mka_new_session)
        finally:
            # Revert back to original configuration
            setup_macsec_configuration(duthost, ctrl_link, profile_name, default_priority,
                                       cipher_suite, primary_cak, primary_ckn, policy, send_sci, rekey_period, tbinfo)
            # Clean up new macsec profile
            delete_macsec_profile(duthost, port_name, new_profile_name)
