"""
=============================================================================
Module: ixia/pfcwd
File: test_pfcwd_burst_storm.py
=============================================================================

Description:
    This test module validates PFC watchdog behavior under bursty PFC storm
    conditions. It tests PFCWD's ability to detect and recover from intermittent
    PFC storms that occur in bursts rather than continuously.

Test Intent:
    - test_pfcwd_burst_storm_single_lossless_prio: Tests PFC watchdog detection
      and recovery when subjected to bursty PFC storms on a single lossless
      priority, ensuring PFCWD handles intermittent storm patterns correctly
    - test_pfcwd_burst_storm_multi_lossless_prio: Validates PFCWD handles
      bursty storms across multiple lossless priorities simultaneously

Topology:
    - tgen: Requires IXIA traffic generator topology

Fixtures Used:
    - ixia_api: IXIA session for traffic generation
    - ixia_testbed_config: Testbed and port configuration
    - conn_graph_facts: DUT-to-IXIA connection topology
    - fanout_graph_facts: Fanout switch information
    - rand_one_dut_lossless_prio: Random lossless priority for testing
    - lossless_prio_list: List of all lossless priorities
    - prio_dscp_map: Priority to DSCP mapping

Dependencies:
    - files.pfcwd_burst_storm_helper: Burst storm test implementation
    - tests.common.ixia.ixia_fixtures: IXIA infrastructure
    - tests.common.ixia.qos_fixtures: QoS test fixtures

Notes:
    - Tests intermittent PFC storms (bursts) rather than continuous storms
    - Validates PFCWD detection threshold logic with bursty patterns
    - Ensures proper recovery between storm bursts
    - More challenging test pattern than continuous storms
=============================================================================
"""
import pytest
import logging

from tests.common.helpers.assertions import pytest_require
from tests.common.fixtures.conn_graph_facts import conn_graph_facts, fanout_graph_facts     # noqa: F401
from tests.common.ixia.ixia_fixtures import ixia_api_serv_ip, ixia_api_serv_port,\
    ixia_api_serv_user, ixia_api_serv_passwd, ixia_api, ixia_testbed_config                 # noqa: F401
from tests.common.ixia.qos_fixtures import prio_dscp_map                                    # noqa: F401
from .files.pfcwd_burst_storm_helper import run_pfcwd_burst_storm_test

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.topology('tgen')]


def test_pfcwd_burst_storm_single_lossless_prio(ixia_api, ixia_testbed_config, conn_graph_facts,        # noqa: F811
                                                fanout_graph_facts, duthosts, rand_one_dut_hostname,    # noqa: F811
                                                rand_one_dut_portname_oper_up, rand_one_dut_lossless_prio,
                                                prio_dscp_map):                                         # noqa: F811

    """
    Test PFC watchdog under bursty PFC storms on a single lossless priority

    Args:
        ixia_api (pytest fixture): IXIA session
        ixia_testbed_config (pytest fixture): testbed configuration information
        conn_graph_facts (pytest fixture): connection graph
        fanout_graph_facts (pytest fixture): fanout graph
        duthosts (pytest fixture): list of DUTs
        rand_one_dut_hostname (str): hostname of DUT
        rand_one_dut_portname_oper_up (str): port to test, e.g., 's6100-1|Ethernet0'
        rand_one_dut_lossless_prio (str): name of lossless priority to test, e.g., 's6100-1|3'
        prio_dscp_map (pytest fixture): priority vs. DSCP map (key = priority)

    Returns:
        N/A
    """
    dut_hostname, dut_port = rand_one_dut_portname_oper_up.split('|')
    dut_hostname2, lossless_prio = rand_one_dut_lossless_prio.split('|')
    pytest_require(rand_one_dut_hostname == dut_hostname == dut_hostname2,
                   "Priority and port are not mapped to the expected DUT")

    duthost = duthosts[rand_one_dut_hostname]

    testbed_config, port_config_list = ixia_testbed_config
    lossless_prio = int(lossless_prio)

    run_pfcwd_burst_storm_test(api=ixia_api,
                               testbed_config=testbed_config,
                               port_config_list=port_config_list,
                               conn_data=conn_graph_facts,
                               fanout_data=fanout_graph_facts,
                               duthost=duthost,
                               dut_port=dut_port,
                               prio_list=[lossless_prio],
                               prio_dscp_map=prio_dscp_map)
