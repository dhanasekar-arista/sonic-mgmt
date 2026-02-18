"""
=============================================================================
Module: platform_tests
File: test_check_sfp_using_ethtool.py
=============================================================================

Description:
    Mellanox-specific test validating SFP/transceiver EEPROM accessibility via
    ethtool. Maps physical ports to sfpN devices and verifies EEPROM readability.

Test Intent:
    - test_check_sfp_using_ethtool: Verify SFP EEPROM is readable via 'ethtool -m sfpN'
      for all connected interfaces

Topology:
    Any topology - Mellanox platforms only

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - rand_one_dut_hostname: Selects one random DUT
    - conn_graph_facts: Connection graph for interface mapping
    - tbinfo: Testbed information
    - xcvr_skip_list: Transceiver skip list

Dependencies:
    - ethtool utility
    - sonic-cfggen for PORT configuration
    - conn_graph_facts for connected interface list
    - SPC3_HWSKUS data for platform-specific lane divider

Notes:
    - Test only runs on Mellanox ASIC platforms
    - SFP ID calculated from port lanes: sfp_id = first_lane/lanes_divider + 1
    - SPC3 platforms use lanes_divider=8, others use lanes_divider=4
    - QSFP-DD cables may show limited ethtool output (0x18 identifier only)
    - Regular transceivers show full parsed EEPROM output (>=5 lines)
    - Skips interfaces in xcvr_skip_list
    - Only tests connected interfaces from conn_graph_facts
    - Test plan reference: https://github.com/sonic-net/SONiC/blob/master/doc/pmon/sonic_platform_test_plan.md
=============================================================================
"""
import logging
import json
import pytest
from tests.common.fixtures.conn_graph_facts import conn_graph_facts     # noqa: F401
from tests.common.mellanox_data import SPC3_HWSKUS
from .check_hw_mgmt_service import check_hw_management_service

pytestmark = [
    pytest.mark.asic('mellanox'),
    pytest.mark.topology('any')
]


def test_check_sfp_using_ethtool(duthosts, rand_one_dut_hostname,
                                 conn_graph_facts, tbinfo, xcvr_skip_list):     # noqa: F811
    """This test case is to check SFP using the ethtool.
    """
    duthost = duthosts[rand_one_dut_hostname]
    ports_config = json.loads(duthost.command(
        "sudo sonic-cfggen -d --var-json PORT")["stdout"])

    logging.info("Use the ethtool to check SFP information")
    if duthost.facts["hwsku"] in SPC3_HWSKUS:
        lanes_divider = 8
    else:
        lanes_divider = 4
    for intf in conn_graph_facts["device_conn"][duthost.hostname]:
        if intf not in xcvr_skip_list[duthost.hostname]:
            intf_lanes = ports_config[intf]["lanes"]
            sfp_id = int(intf_lanes.split(",")[0])//lanes_divider + 1

            ethtool_sfp_output = duthost.command(
                "sudo ethtool -m sfp%s" % str(sfp_id))
            assert ethtool_sfp_output["rc"] == 0, "Failed to read eeprom of sfp%s using ethtool" % str(
                sfp_id)
            # QSFP-DD cable case (currenly ethtool not supporting a full parser)
            if len(ethtool_sfp_output["stdout_lines"]) == 1:
                assert '0x18' in str(ethtool_sfp_output["stdout_lines"]), \
                    "Does the ethtool output look normal? " + \
                    str(ethtool_sfp_output["stdout_lines"])
            else:
                assert len(ethtool_sfp_output["stdout_lines"]) >= 5, \
                    "Does the ethtool output look normal? " + \
                    str(ethtool_sfp_output["stdout_lines"])
                for line in ethtool_sfp_output["stdout_lines"]:
                    assert len(line.split(":")) >= 2, \
                        "Unexpected line %s in %s" % (
                            line, str(ethtool_sfp_output["stdout_lines"]))

    logging.info("Check interface status")
    mg_facts = duthost.get_extended_minigraph_facts(tbinfo)
    intf_facts = duthost.interface_facts(
        up_ports=mg_facts["minigraph_ports"])["ansible_facts"]
    assert len(intf_facts["ansible_interface_link_down_ports"]) == 0, \
        "Some interfaces are down: %s" % str(
            intf_facts["ansible_interface_link_down_ports"])

    check_hw_management_service(duthost)
