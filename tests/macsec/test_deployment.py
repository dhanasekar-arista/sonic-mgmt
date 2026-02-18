"""
=============================================================================
Module: macsec
File: test_deployment.py
=============================================================================

Description:
    This test validates MACsec deployment scenarios including configuration
    persistence across config reload and scale rekey operations when multiple
    MACsec sessions are shut down and brought back up simultaneously.

Test Intent:
    - test_config_reload: Validates MACsec configuration persistence across
      config reload. Saves current config, performs config reload, and verifies
      APPL_DB MACsec entries are restored with correct policy, cipher suite,
      and send_sci settings within 300 seconds.
    - test_scale_rekey: Tests MACsec rekey at scale by shutting down all
      controlled links simultaneously, waiting for MKA timeout, bringing
      interfaces back up, and verifying new SA tables are established. If
      rekey_period is configured, waits for automatic rekey and verifies
      SA tables change again, demonstrating MACsec resilience at scale.

Topology:
    t0, t2, t0-sonic topologies with MACsec support required

Fixtures Used:
    - duthost: DUT host object for test execution
    - ctrl_links: Dictionary of MACsec-controlled links on the DUT
    - policy: MACsec policy configuration
    - cipher_suite: MACsec cipher suite (e.g., GCM-AES-128, GCM-AES-256)
    - send_sci: Whether to send SCI in MACsec frames
    - wait_mka_establish: Waits for MKA session establishment before tests
    - rekey_period: Period for automatic key rotation

Dependencies:
    - tests.common.utilities: For wait_until polling functionality
    - tests.common.config_reload: For configuration reload operations
    - tests.common.macsec.macsec_helper: APPL_DB validation and data retrieval

Notes:
    - MKA_TIMEOUT is 6 seconds
    - test_config_reload saves original config and restores it after test
    - test_config_reload disables loganalyzer
    - test_config_reload waits up to 300 seconds for APPL_DB restoration
    - test_scale_rekey shuts down all controlled links simultaneously
    - test_scale_rekey waits 30 seconds for new MKA session after interface startup
    - If rekey_period is non-zero, waits 2x rekey_period for automatic rekey
    - test_scale_rekey disables loganalyzer
    - Validates SA table changes to confirm new MKA sessions established
=============================================================================
"""
import pytest
import logging

from tests.common.utilities import wait_until
from tests.common import config_reload
from tests.common.macsec.macsec_helper import check_appl_db, get_appl_db
from time import sleep
logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.macsec_required,
    pytest.mark.topology("t0", "t2", "t0-sonic"),
]


class TestDeployment():
    MKA_TIMEOUT = 6

    @pytest.mark.disable_loganalyzer
    def test_config_reload(self, duthost, ctrl_links, policy, cipher_suite, send_sci, wait_mka_establish):
        # Save the original config file
        duthost.shell("cp /etc/sonic/config_db*.json /tmp")
        # Save the current config file
        duthost.shell("config save -y")
        config_reload(duthost)
        assert wait_until(300, 6, 12, check_appl_db, duthost, ctrl_links, policy, cipher_suite, send_sci)
        # Recover the original config file
        duthost.shell("sudo mv /tmp/config_db*.json /etc/sonic")

    @pytest.mark.disable_loganalyzer
    def test_scale_rekey(self, duthost, ctrl_links, rekey_period, wait_mka_establish):
        dut_egress_sa_table_orig = {}
        dut_ingress_sa_table_orig = {}
        dut_egress_sa_table_current = {}
        dut_ingress_sa_table_current = {}
        new_dut_egress_sa_table = {}
        new_dut_ingress_sa_table = {}

        # Shut the interface and wait for all macsec sessions to be down
        for dut_port, nbr in ctrl_links.items():
            _, _, _, dut_egress_sa_table_orig[dut_port], dut_ingress_sa_table_orig[dut_port] = get_appl_db(
                duthost, dut_port, nbr["host"], nbr["port"])
            intf_asic = duthost.get_port_asic_instance(dut_port)
            intf_asic.shutdown_interface(dut_port)

        sleep(TestDeployment.MKA_TIMEOUT)

        # Unshut the interfaces so that macsec sessions come back up
        for dut_port, nbr in ctrl_links.items():
            intf_asic = duthost.get_port_asic_instance(dut_port)
            intf_asic.startup_interface(dut_port)

        for dut_port, nbr in ctrl_links.items():
            def check_new_mka_session():
                _, _, _, dut_egress_sa_table_current[dut_port], dut_ingress_sa_table_current[dut_port] = get_appl_db(
                    duthost, dut_port, nbr["host"], nbr["port"])
                if dut_egress_sa_table_orig[dut_port] and dut_egress_sa_table_current[dut_port]:
                    assert dut_egress_sa_table_orig[dut_port] != dut_egress_sa_table_current[dut_port]
                if dut_ingress_sa_table_orig[dut_port] and dut_ingress_sa_table_current[dut_port]:
                    assert dut_ingress_sa_table_orig[dut_port] != dut_ingress_sa_table_current[dut_port]
                return True
            assert wait_until(30, 2, 2, check_new_mka_session)

        # if rekey_period for the profile is valid, Wait for rekey and make sure all sessions are present
        if rekey_period != 0:
            sleep(rekey_period * 2)

            for dut_port, nbr in ctrl_links.items():
                _, _, _, new_dut_egress_sa_table[dut_port], new_dut_ingress_sa_table[dut_port] = get_appl_db(
                    duthost, dut_port, nbr["host"], nbr["port"])
                if dut_egress_sa_table_current[dut_port] and new_dut_egress_sa_table[dut_port]:
                    assert dut_egress_sa_table_current[dut_port] != new_dut_egress_sa_table[dut_port]
                if dut_ingress_sa_table_current[dut_port] and new_dut_ingress_sa_table[dut_port]:
                    assert dut_ingress_sa_table_current[dut_port] != new_dut_ingress_sa_table[dut_port]
