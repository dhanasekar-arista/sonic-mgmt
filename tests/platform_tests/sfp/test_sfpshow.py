"""
=============================================================================
Module: platform_tests
File: test_sfpshow.py
=============================================================================

Description:
    Tests SFP/transceiver status using legacy sfpshow CLI tool. Validates transceiver
    presence and EEPROM data. Covers 'Check SFP status and configure SFP' test case
    from SONiC platform test plan.

Test Intent:
    - test_check_sfp_presence: Verify transceiver presence via 'sfpshow presence'
    - test_check_sfp_eeprom: Validate EEPROM data via 'sfpshow eeprom'

Topology:
    Any topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one frontend DUT per hardware SKU
    - enum_frontend_asic_index: Frontend ASIC index
    - conn_graph_facts: Connection graph for port mapping
    - xcvr_skip_list: Transceiver skip list

Dependencies:
    - sfpshow CLI commands (legacy tool)
    - parse_eeprom, parse_output, get_dev_conn helpers

Notes:
    - sfpshow is legacy tool, newer systems use 'show interface transceiver'
    - Test validates transceiver presence matches expected connected ports
    - EEPROM validation checks for valid data fields
    - Skips interfaces in xcvr_skip_list
    - Loganalyzer disabled (transceivers may generate expected logs)
    - Test plan: https://github.com/sonic-net/SONiC/blob/master/doc/pmon/sonic_platform_test_plan.md
=============================================================================
"""

import logging
import pytest

from .util import parse_eeprom
from .util import parse_output
from .util import get_dev_conn

cmd_sfp_presence = "sudo sfpshow presence"
cmd_sfp_eeprom = "sudo sfpshow eeprom"


pytestmark = [
    pytest.mark.disable_loganalyzer,  # disable automatic loganalyzer
    pytest.mark.topology('any')
]


def test_check_sfp_presence(duthosts, enum_rand_one_per_hwsku_frontend_hostname,
                            enum_frontend_asic_index, conn_graph_facts, xcvr_skip_list):
    """
    @summary: Check SFP presence using 'sfputil show presence'
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    global ans_host
    ans_host = duthost
    portmap, dev_conn = get_dev_conn(duthost, conn_graph_facts, enum_frontend_asic_index)

    logging.info("Check output of '{}'".format(cmd_sfp_presence))
    sfp_presence = duthost.command(cmd_sfp_presence)
    parsed_presence = parse_output(sfp_presence["stdout_lines"][2:])
    for intf in dev_conn:
        if intf not in xcvr_skip_list[duthost.hostname]:
            assert intf in parsed_presence, (
                "Interface '{}' is not in the output of '{}'. "
                "Parsed presence output: {}".format(intf, cmd_sfp_presence, parsed_presence)
            )
            assert parsed_presence[intf] == "Present", \
                "Interface '{}' presence is not 'Present'. Actual value: '{}'.".format(
                    intf, parsed_presence.get(intf)
            )


def test_check_sfpshow_eeprom(duthosts, enum_rand_one_per_hwsku_frontend_hostname,
                              enum_frontend_asic_index, conn_graph_facts, xcvr_skip_list):
    """
    @summary: Check SFP presence using 'sfputil show presence'
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    global ans_host
    ans_host = duthost
    portmap, dev_conn = get_dev_conn(duthost, conn_graph_facts, enum_frontend_asic_index)

    logging.info("Check output of '{}'".format(cmd_sfp_eeprom))
    sfp_eeprom = duthost.command(cmd_sfp_eeprom)
    parsed_eeprom = parse_eeprom(sfp_eeprom["stdout_lines"])
    for intf in dev_conn:
        if intf not in xcvr_skip_list[duthost.hostname]:
            assert intf in parsed_eeprom, "Interface '{}' not found in 'sfputil show eeprom' output.".format(intf)
            assert parsed_eeprom[intf] == "SFP EEPROM detected", (
                (
                    "The EEPROM information for interface '{}' is not as expected. "
                    "Expected: 'SFP EEPROM detected', but got: '{}'. "
                    "Full parsed EEPROM output: {}"
                ).format(intf, parsed_eeprom.get(intf, "No data found"), parsed_eeprom)
            )
