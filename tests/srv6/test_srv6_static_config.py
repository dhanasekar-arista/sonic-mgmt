"""
=============================================================================
Module: srv6
File: test_srv6_static_config.py
=============================================================================

Description:
    This test module validates static SRv6 configuration on SONiC switches via
    CONFIG_DB manipulation. It tests locator and MY_SID configuration through
    direct database entries, verifying that bgpcfgd correctly generates FRR
    configuration and programs APPL_DB with SRv6 endpoint behavior settings.

Test Intent:
    - test_uN_config: Validates static SRv6 configuration by adding locator and
      uN (endpoint with next-header decapsulation) SID entries to CONFIG_DB,
      verifying bgpcfgd generates correct FRR configuration, and confirming
      APPL_DB is properly programmed with SID behavior information

Topology:
    - Supported: t0, t1
    - Works on both single-ASIC and multi-ASIC platforms

Fixtures Used:
    - duthosts: All DUT hosts in testbed
    - enum_frontend_dut_hostname: Frontend DUT selection
    - enum_rand_one_asic_index: Random ASIC instance selection for multi-ASIC

Dependencies:
    - srv6_utils: SRv6 validation utilities for APPL_DB verification
    - tests.common.utilities: Wait and retry utilities
    - bgpcfgd: BGP configuration daemon for FRR config generation

Notes:
    - Configuration tables used:
      - SRV6_MY_LOCATORS: Locator prefix and function length
      - SRV6_MY_SIDS: SID action and behavior parameters
    - Test locator: fcbb:bbbb:1:: with func_len 0
    - Test SID: fcbb:bbbb:1::/48 with uN behavior
    - SID parameters: action=uN, decap_dscp_mode=pipe
    - Wait time between operations: 5 seconds
    - FRR config verification includes "locator loc1" and "behavior uN" clauses
    - APPL_DB verification timeout: 60 seconds with 2-second polling
    - Multi-ASIC: uses namespace-specific sonic-db-cli and vtysh commands
    - uN behavior: decapsulates outer IPv6 header, forwards based on inner header
    - DSCP mode pipe: copies DSCP from inner header to outer after decapsulation
=============================================================================
"""

import time
import pytest
from tests.common.utilities import wait_until
from srv6_utils import verify_appl_db_sid_entry_exist

pytestmark = [
    pytest.mark.topology('t0', 't1')
]

WAIT_TIME = 5


def test_uN_config(duthosts, enum_frontend_dut_hostname, enum_rand_one_asic_index):
    duthost = duthosts[enum_frontend_dut_hostname]
    asic_index = enum_rand_one_asic_index

    if duthost.is_multi_asic:
        cli_options = " -n " + duthost.get_namespace_from_asic_id(asic_index)
    else:
        cli_options = ''

    sonic_db_cli = "sonic-db-cli" + cli_options
    vtysh_shell = "vtysh" + cli_options

    # add a locator configuration entry
    duthost.command(sonic_db_cli + " CONFIG_DB HSET SRV6_MY_LOCATORS\\|loc1 prefix fcbb:bbbb:1:: func_len 0")
    time.sleep(WAIT_TIME)
    # add a uN sid configuration entry
    duthost.command(sonic_db_cli +
                    " CONFIG_DB HSET SRV6_MY_SIDS\\|loc1\\|fcbb:bbbb:1::/48 action uN decap_dscp_mode pipe")
    time.sleep(WAIT_TIME)

    frr_config = duthost.command(vtysh_shell + " -c \"show running-config\"")["stdout"]

    # verify that bgpcfgd generates FRR config correctly
    assert "locator loc1" in frr_config, "Locator is missing in FRR's configuration"
    assert "sid fcbb:bbbb:1::/48 locator loc1 behavior uN" in frr_config, "SID is missing in FRR's configuration"

    # verify that APPL_DB gets programmed by FRR correctly
    assert wait_until(60, 2, 0, verify_appl_db_sid_entry_exist, duthost, sonic_db_cli,
                      "SRV6_MY_SID_TABLE:32:16:0:0:fcbb:bbbb:1::", True), "SID is missing in APPL_DB"
    assert "un" == duthost.command(sonic_db_cli +
                                   " APPL_DB hget SRV6_MY_SID_TABLE:32:16:0:0:fcbb:bbbb:1:: action")["stdout"], \
        "SID entry in APPL_DB was not programmed correctly"

    # delete the configurations
    duthost.command(sonic_db_cli + " CONFIG_DB DEL SRV6_MY_SIDS\\|loc1\\|fcbb:bbbb:1::/48")
    time.sleep(WAIT_TIME)
    duthost.command(sonic_db_cli + " CONFIG_DB DEL SRV6_MY_LOCATORS\\|loc1")
    time.sleep(WAIT_TIME)

    frr_config = duthost.command(vtysh_shell + " -c \"show running-config\"")["stdout"]

    # verify that bgpcfgd deletes relevant FRR config
    assert "locator loc1" not in frr_config, "Locator was not cleaned up in FRR's configuration"
    assert "sid fcbb:bbbb:1::/48 locator loc1 behavior uN" not in frr_config, \
        "SID entry was not cleaned up in FRR's configuration"

    # verify that the APPL_DB entry gets cleaned correctly
    assert wait_until(60, 2, 0, verify_appl_db_sid_entry_exist, duthost, sonic_db_cli,
                      "SRV6_MY_SID_TABLE:32:16:0:0:fcbb:bbbb:1::", False), \
        "SID entry in APPL_DB was not cleaned up"


@pytest.mark.asic('vs')
def test_uDT46_config(duthosts, enum_frontend_dut_hostname, enum_rand_one_asic_index):
    duthost = duthosts[enum_frontend_dut_hostname]
    asic_index = enum_rand_one_asic_index

    if duthost.is_multi_asic:
        cli_options = " -n " + duthost.get_namespace_from_asic_id(asic_index)
    else:
        cli_options = ''

    sonic_db_cli = "sonic-db-cli" + cli_options
    vtysh_shell = "vtysh" + cli_options

    # add Vrf1 config
    duthost.command("config vrf add Vrf1")
    duthost.command("sysctl -w net.vrf.strict_mode=1")
    time.sleep(WAIT_TIME)

    # add a locator configuration entry
    duthost.command(sonic_db_cli + " CONFIG_DB HSET SRV6_MY_LOCATORS\\|loc1 prefix fcbb:bbbb:1::")
    # add a uDT46 sid configuration entry
    duthost.command(sonic_db_cli + " CONFIG_DB HSET SRV6_MY_SIDS\\|loc1\\|fcbb:bbbb:1:2::/64 \
                    action uDT46 decap_vrf Vrf1 decap_dscp_mode uniform")
    time.sleep(WAIT_TIME)

    frr_config = duthost.command(vtysh_shell + " -c \"show running-config\"")["stdout"]

    # verify that bgpcfgd generates FRR config correctly
    assert "locator loc1" in frr_config, "Locator is missing in FRR's configuration"
    assert "sid fcbb:bbbb:1:2::/64 locator loc1 behavior uDT46 vrf Vrf1" in frr_config, \
        "SID is missing in FRR's configuration"

    # verify that APPL_DB gets programmed by FRR correctly
    assert wait_until(60, 2, 0, verify_appl_db_sid_entry_exist, duthost, sonic_db_cli,
                      "SRV6_MY_SID_TABLE:32:16:16:0:fcbb:bbbb:1:2::", True), "SID is missing in APPL_DB"
    assert "udt46" == duthost.command(sonic_db_cli +
                                      " APPL_DB hget SRV6_MY_SID_TABLE:32:16:16:0:fcbb:bbbb:1:2:: action")["stdout"], \
        "SID entry in APPL_DB was not programmed correctly"
    assert "Vrf1" == duthost.command(sonic_db_cli +
                                     " APPL_DB hget SRV6_MY_SID_TABLE:32:16:16:0:fcbb:bbbb:1:2:: vrf")["stdout"], \
        "SID entry in APPL_DB was not programmed correctly"

    # delete the configurations
    duthost.command(sonic_db_cli + " CONFIG_DB DEL SRV6_MY_SIDS\\|loc1\\|fcbb:bbbb:1:2::/64")
    time.sleep(WAIT_TIME)
    duthost.command(sonic_db_cli + " CONFIG_DB DEL SRV6_MY_LOCATORS\\|loc1")
    time.sleep(WAIT_TIME)

    frr_config = duthost.command(vtysh_shell + " -c \"show running-config\"")["stdout"]

    # verify that bgpcfgd deletes relevant FRR config
    assert "locator loc1" not in frr_config, "Locator was not cleaned up in FRR's configuration"
    assert "sid fcbb:bbbb:1:2::/64 locator loc1 behavior uDT46 vrf Vrf1" not in frr_config, \
        "SID entry was not cleaned up in FRR's configuration"

    # verify that the APPL_DB entry gets cleaned correctly
    assert wait_until(60, 2, 0, verify_appl_db_sid_entry_exist, duthost, sonic_db_cli,
                      "SRV6_MY_SID_TABLE:32:16:16:0:fcbb:bbbb:1:2::", False), "SID entry in APPL_DB was not cleaned up"

    # delete the Vrf config
    duthost.command("config vrf del Vrf1")
