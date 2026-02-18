"""
=============================================================================
Module: ixia/pfcwd
File: test_pfcwd_runtime_traffic.py
=============================================================================

Description:
    This test module validates the impact of PFC watchdog operations on
    runtime traffic. It ensures that PFCWD detection and recovery actions
    do not disrupt traffic on unaffected priorities.

Test Intent:
    - test_pfcwd_runtime_traffic: Tests PFC watchdog's impact on runtime
      traffic across all priorities, ensuring PFCWD actions are isolated
      to affected priorities and don't cause collateral traffic disruption

Topology:
    - tgen: Requires IXIA traffic generator topology

Fixtures Used:
    - ixia_api: IXIA session for traffic generation
    - ixia_testbed_config: Testbed and port configuration
    - conn_graph_facts: DUT-to-IXIA connection topology
    - fanout_graph_facts: Fanout switch information
    - all_prio_list: List of all priorities to test
    - prio_dscp_map: Priority to DSCP mapping

Dependencies:
    - files.pfcwd_runtime_traffic_helper: Runtime traffic test implementation
    - tests.common.ixia.ixia_fixtures: IXIA infrastructure
    - tests.common.ixia.qos_fixtures: QoS test fixtures

Notes:
    - Validates traffic continues on non-storm-affected priorities
    - Tests PFCWD isolation - only affected priority should be impacted
    - Ensures PFCWD recovery restores full traffic functionality
    - Critical test for production readiness validation
=============================================================================
"""
import pytest

from tests.common.helpers.assertions import pytest_require
from tests.common.fixtures.conn_graph_facts import conn_graph_facts, fanout_graph_facts     # noqa: F401
from tests.common.ixia.ixia_fixtures import ixia_api_serv_ip, ixia_api_serv_port,\
    ixia_api_serv_user, ixia_api_serv_passwd, ixia_api, ixia_testbed_config                 # noqa: F401
from tests.common.ixia.qos_fixtures import prio_dscp_map, all_prio_list                     # noqa: F401

from .files.pfcwd_runtime_traffic_helper import run_pfcwd_runtime_traffic_test

pytestmark = [pytest.mark.topology('tgen')]


def test_pfcwd_runtime_traffic(ixia_api, ixia_testbed_config, conn_graph_facts, fanout_graph_facts,     # noqa: F811
                               duthosts, rand_one_dut_hostname, rand_one_dut_portname_oper_up,
                               all_prio_list, prio_dscp_map):                                           # noqa: F811
    """
    Test PFC watchdog's impact on runtime traffic

    Args:
        ixia_api (pytest fixture): IXIA session
        ixia_testbed_config (pytest fixture): testbed configuration information
        conn_graph_facts (pytest fixture): connection graph
        fanout_graph_facts (pytest fixture): fanout graph
        duthosts (pytest fixture): list of DUTs
        rand_one_dut_hostname (str): hostname of DUT
        rand_one_dut_portname_oper_up (str): port to test, e.g., 's6100-1|Ethernet0'
        all_prio_list (pytest fixture): list of all the priorities
        prio_dscp_map (pytest fixture): priority vs. DSCP map (key = priority)

    Returns:
        N/A
    """
    dut_hostname, dut_port = rand_one_dut_portname_oper_up.split('|')
    pytest_require(rand_one_dut_hostname == dut_hostname,
                   "Port is not mapped to the expected DUT")

    duthost = duthosts[rand_one_dut_hostname]
    testbed_config, port_config_list = ixia_testbed_config

    run_pfcwd_runtime_traffic_test(api=ixia_api,
                                   testbed_config=testbed_config,
                                   port_config_list=port_config_list,
                                   conn_data=conn_graph_facts,
                                   fanout_data=fanout_graph_facts,
                                   duthost=duthost,
                                   dut_port=dut_port,
                                   prio_list=all_prio_list,
                                   prio_dscp_map=prio_dscp_map)
