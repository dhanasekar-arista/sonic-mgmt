"""
=============================================================================
Module: platform_tests
File: test_xcvr_info_in_db.py
=============================================================================

Description:
    Tests xcvrd daemon functionality by validating transceiver information in database.
    Verifies xcvrd properly populates STATE_DB with transceiver status, EEPROM data, and
    DOM values. Covers 'Check xcvrd information in DB' test case from SONiC platform test plan.

Test Intent:
    - test_xcvr_info_in_db: Verify xcvrd populates STATE_DB with correct transceiver information

Topology:
    Any topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one frontend DUT per hardware SKU
    - enum_frontend_asic_index: Frontend ASIC index
    - conn_graph_facts: Connection graph for interface validation
    - xcvr_skip_list: Transceiver skip list
    - port_list_with_flat_memory: Ports with flat memory (skip DOM checks)

Dependencies:
    - xcvrd daemon in pmon container
    - STATE_DB for transceiver data
    - check_transceiver_status validator
    - get_port_map for port mapping
    - get_lport_to_first_subport_mapping for logical port mapping

Notes:
    - Test waits for pmon uptime > minimum threshold (360s wait, 10s interval)
    - Validates transceiver status in STATE_DB for all connected interfaces
    - Skips interfaces in xcvr_skip_list
    - Skips ports with flat memory (no DOM support)
    - For multi-ASIC: validates only interfaces on specified ASIC
    - Uses wait_until for asynchronous checks
    - Test plan: https://github.com/sonic-net/SONiC/blob/master/doc/pmon/sonic_platform_test_plan.md
=============================================================================
"""
import logging
import pytest
from tests.common.platform.transceiver_utils import check_transceiver_status
from tests.common.platform.interface_utils import get_port_map, get_lport_to_first_subport_mapping
from tests.common.fixtures.conn_graph_facts import conn_graph_facts     # noqa F401
from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from tests.common.platform.processes_utils import check_pmon_uptime_minutes

pytestmark = [
    pytest.mark.topology('any')
]


def test_xcvr_info_in_db(duthosts, enum_rand_one_per_hwsku_frontend_hostname,
                         enum_frontend_asic_index,
                         conn_graph_facts, xcvr_skip_list, port_list_with_flat_memory):   # noqa: F811
    """
    @summary: This test case is to verify that xcvrd works as expected by checking transceiver information in DB
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]

    pytest_assert(wait_until(360, 10, 0, check_pmon_uptime_minutes, duthost),
                  "Pmon docker is not ready for test")

    logging.info("Check transceiver status")
    all_interfaces = conn_graph_facts.get("device_conn", {}).get(duthost.hostname, {})

    if enum_frontend_asic_index is not None:
        # Get the interface pertaining to that asic
        interface_list = get_port_map(duthost, enum_frontend_asic_index)

        # Check if the interfaces of this AISC is present in conn_graph_facts
        all_interfaces = {k: v for k, v in list(interface_list.items())
                          if k in conn_graph_facts.get("device_conn", {}).get(duthost.hostname, {})}
        logging.info("ASIC {} interface_list {}".format(
            enum_frontend_asic_index, all_interfaces))

    # Get the first subport of the logical port since DOM is returned only for first subport.
    lport_to_first_subport_mapping = get_lport_to_first_subport_mapping(duthost, all_interfaces)
    check_transceiver_status(duthost, enum_frontend_asic_index, all_interfaces, xcvr_skip_list,
                             port_list_with_flat_memory, lport_to_first_subport_mapping)
