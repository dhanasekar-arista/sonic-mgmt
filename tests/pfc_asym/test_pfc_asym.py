"""
=============================================================================
Module: pfc_asym
File: test_pfc_asym.py
=============================================================================

Description:
    This test suite validates Asymmetric Priority Flow Control (PFC) functionality
    in SONiC. Asymmetric PFC allows separate control of PFC frame transmission and
    reception on priorities. When enabled, DUT can respond to PFC frames on all
    priorities while only generating PFC on lossless priorities. Tests verify PFC
    behavior with asymmetric mode disabled and enabled.

Test Intent:
    - test_pfc_asym_off_tx_pfc: Verify DUT generates PFC only on lossless priorities when asymmetric PFC is disabled
    - test_pfc_asym_off_rx_pause_frames: Verify DUT drops packets only for lossless priorities when receiving PFC frames with asymmetric mode disabled
    - test_pfc_asym_on_tx_pfc: Verify DUT generates PFC only on lossless priorities when asymmetric PFC is enabled
    - test_pfc_asym_on_handle_pfc_all_prio: Verify DUT handles PFC frames on all priorities when asymmetric mode is enabled

Topology:
    t0 - Requires T0 topology with server and non-server ports

Fixtures Used:
    - setup: Performs setup/teardown for test case preparation including PTF test parameters
    - enable_pfc_asym: Enables/disables asymmetric PFC on all server interfaces
    - pfc_storm_runner: Starts/stops PFC frame generator on fanout switch
    - swapSyncd: Swaps syncd for testing
    - ptfhost: PTF host for running traffic tests

Dependencies:
    - tests.ptf_runner: Runs PTF test scripts
    - tests.common.fixtures.pfc_asym: Provides setup fixture for PFC asymmetric testing
    - PTF test scripts: pfc_asym.PfcAsymOffOnTxTest, pfc_asym.PfcAsymOffRxTest, pfc_asym.PfcAsymOnRxTest

Notes:
    - Asymmetric PFC allows different behavior for TX (generate) vs RX (respond to) PFC frames
    - When disabled: DUT only responds to PFC on lossless priorities
    - When enabled: DUT responds to PFC on all priorities but only generates PFC on lossless
    - PFC storm generator creates backpressure to trigger PFC frame generation
    - server_ports flag indicates tests on server-facing ports
    - non_server_port flag indicates tests on non-server-facing ports
    - Tests verify correct queue pause behavior and packet drop patterns
    - PTF scripts validate PFC frame generation and reception behavior
=============================================================================
"""
from tests.ptf_runner import ptf_runner
from tests.common.fixtures.pfc_asym import setup    # noqa: F401
import pytest

pytestmark = [
    pytest.mark.topology('t0')
]


@pytest.fixture(scope='module', autouse=True)
def prepare_syncdrpc(swapSyncd):
    pass


def test_pfc_asym_off_tx_pfc(ptfhost, setup, pfc_storm_runner):     # noqa: F811
    """
    @summary: Asymmetric PFC is disabled. Verify that DUT generates PFC frames only on lossless priorities when
                asymmetric PFC is disabled
    @param ptfhost: Fixture which can run ansible modules on the PTF host
    @param setup: Fixture which performs setup/tardown steps needed for test case preparation
    """
    pfc_storm_runner.non_server_port = True
    pfc_storm_runner.run()

    ptf_runner(ptfhost,
               "saitests",
               "pfc_asym.PfcAsymOffOnTxTest",
               platform_dir="ptftests",
               params=setup["ptf_test_params"],
               log_file="/tmp/pfc_asym.PfcAsymOffOnTxTest.log")


def test_pfc_asym_off_rx_pause_frames(ptfhost, setup, pfc_storm_runner):        # noqa: F811
    """
    @summary: Asymmetric PFC is disabled. Verify that while receiving PFC frames DUT drops packets only for lossless
                priorities (RX and Tx queue buffers are full)
    @param ptfhost: Fixture which can run ansible modules on the PTF host
    @param setup: Fixture which performs setup/tardown steps needed for test case preparation
    @param pfc_storm_runner: Fixture which start/stop PFC generator on Fanout switch
    """
    pfc_storm_runner.server_ports = True
    pfc_storm_runner.run()

    ptf_runner(ptfhost,
               "saitests",
               "pfc_asym.PfcAsymOffRxTest",
               platform_dir="ptftests",
               params=setup["ptf_test_params"],
               log_file="/tmp/pfc_asym.PfcAsymOffRxTest.log")


def test_pfc_asym_on_tx_pfc(ptfhost, setup, enable_pfc_asym, pfc_storm_runner):     # noqa: F811
    """
    @summary: Asymmetric PFC is enabled. Verify that DUT generates PFC frames only on lossless priorities when
                asymmetric PFC is enabled
    @param ptfhost: Fixture which can run ansible modules on the PTF host
    @param setup: Fixture which performs setup/tardown steps needed for test case preparation
    @param enable_pfc_asym: Fixture which enable/disable asymmetric PFC on all server interfaces
    """
    pfc_storm_runner.non_server_port = True
    pfc_storm_runner.run()

    ptf_runner(ptfhost,
               "saitests",
               "pfc_asym.PfcAsymOffOnTxTest",
               platform_dir="ptftests",
               params=setup["ptf_test_params"],
               log_file="/tmp/pfc_asym.PfcAsymOffOnTxTest.log")


def test_pfc_asym_on_handle_pfc_all_prio(ptfhost, setup, enable_pfc_asym, pfc_storm_runner):        # noqa: F811
    """
    @summary: Asymmetric PFC is enabled. Verify that while receiving PFC frames DUT handle PFC frames on all
                priorities when asymetric mode is enabled
    @param ptfhost: Fixture which can run ansible modules on the PTF host
    @param setup: Fixture which performs setup/tardown steps needed for test case preparation
    @param pfc_storm_runner: Fixture which start/stop PFC generator on Fanout switch
    @param enable_pfc_asym: Fixture which enable/disable asymmetric PFC on all server interfaces
    """
    pfc_storm_runner.server_ports = True
    pfc_storm_runner.run()

    ptf_runner(ptfhost,
               "saitests",
               "pfc_asym.PfcAsymOnRxTest",
               platform_dir="ptftests",
               params=setup["ptf_test_params"],
               log_file="/tmp/pfc_asym.PfcAsymOnRxTest.log")
