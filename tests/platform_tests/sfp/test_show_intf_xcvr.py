"""
=============================================================================
Module: platform_tests
File: test_show_intf_xcvr.py
=============================================================================

Description:
    Tests SFP/transceiver status using 'show interface transceiver' CLI commands.
    Validates transceiver presence, EEPROM data, and low-power mode status. Covers
    'Check SFP status and configure SFP' test case from SONiC platform test plan.

Test Intent:
    - test_check_sfp_presence: Verify transceiver presence via 'show interface transceiver presence'
    - test_check_sfp_eeprom: Validate EEPROM data via 'show interface transceiver eeprom'
    - test_check_sfp_lpmode: Test low-power mode status via 'show interface transceiver lpmode'

Topology:
    Any topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one frontend DUT per hardware SKU
    - enum_frontend_asic_index: Frontend ASIC index
    - conn_graph_facts: Connection graph for port mapping
    - xcvr_skip_list: Transceiver skip list

Dependencies:
    - show interface transceiver CLI commands
    - parse_eeprom, parse_output, get_dev_conn, validate_transceiver_lpmode helpers

Notes:
    - Test validates transceiver presence matches expected connected ports
    - EEPROM validation checks for valid data fields
    - Low-power mode test validates lpmode status for QSFP/OSFP modules
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
from .util import validate_transceiver_lpmode

cmd_sfp_presence = "show interface transceiver presence"
cmd_sfp_eeprom = "show interface transceiver eeprom"
cmd_sfp_lpmode = "show interface transceiver lpmode"

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
                "Interface '{}' is not in output of '{}'."
            ).format(intf, cmd_sfp_presence)

            assert parsed_presence[intf] == "Present", (
                "Interface presence is not 'Present' for '{}'. Got: '{}'. "
            ).format(
                intf,
                parsed_presence[intf]
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
            assert intf in parsed_eeprom, (
                "Interface '{}' is not in output of 'sfputil show eeprom'."
            ).format(intf)

            assert parsed_eeprom[intf] == "SFP EEPROM detected", (
                "EEPROM status check failed for interface '{}'. Expected: 'SFP EEPROM detected', but got: '{}'. "
                "- Parsed EEPROM Output: {}\n"
                "- Command Executed: '{}'"
            ).format(
                intf,
                parsed_eeprom[intf],
                parsed_eeprom,
                cmd_sfp_eeprom
            )


def test_check_show_lpmode(duthosts, enum_rand_one_per_hwsku_frontend_hostname,
                           enum_frontend_asic_index, conn_graph_facts, xcvr_skip_list):
    """
    Verify port mode in 'show interface transceiver lpmode'
    Args:
    - duthosts: dictionary containing DUT hosts
    - enum_rand_one_per_hwsku_frontend_hostname: enumeration to select one DUT per hardware SKU
    - enum_frontend_asic_index: enumeration for frontend ASIC index
    - conn_graph_facts: facts about connectivity graph
    Returns:
    - None
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    portmap, dev_conn = get_dev_conn(
        duthost, conn_graph_facts, enum_frontend_asic_index)
    sfp_lpmode = duthost.command(cmd_sfp_lpmode, module_ignore_errors=True)

    # For vs testbed, we will get expected Error code `ERROR_CHASSIS_LOAD = 2` here.
    if duthost.facts["asic_type"] == "vs" and sfp_lpmode['rc'] == 2:
        return
    assert sfp_lpmode['rc'] == 0, (
        "Run command '{}' failed with return code {}."
    ).format(cmd_sfp_lpmode, sfp_lpmode['rc'])

    sfp_lpmode_data = sfp_lpmode["stdout_lines"]

    # Check if the header is present
    header = sfp_lpmode_data[0]
    logging.info(f"The header is: {header}")
    if header.replace(" ", "") != "Port        Low-power Mode".replace(" ", ""):
        logging.error("Invalid output format: Header missing")
        return False

    # Check interface lpmode
    sfp_lpmode_info = parse_output(sfp_lpmode_data[2:])
    logging.info(f"The interface sfp lpmode info is: {sfp_lpmode_info}")
    for intf in dev_conn:
        if intf not in xcvr_skip_list[duthost.hostname]:
            assert validate_transceiver_lpmode(
                sfp_lpmode_info, intf
            ), (
                "Interface mode incorrect in 'show interface transceiver lpmode' for '{}'. "
            ).format(intf)
