"""
=============================================================================
Module: ixia/pfcwd
File: test_pfcwd_basic.py
=============================================================================

Description:
    This comprehensive test module validates basic PFC watchdog functionality
    including storm detection, recovery, and configuration persistence across
    reboots. It tests PFCWD on individual lossless priorities and verifies
    proper handling of PFC storms.

Test Intent:
    - test_pfcwd_basic_single_lossless_prio: Validates basic PFCWD functionality
      on a single lossless priority with parametrized storm triggering
    - test_pfcwd_basic_multi_lossless_prio: Tests PFCWD across multiple lossless
      priorities simultaneously
    - test_pfcwd_basic_reboot: Verifies PFCWD configuration and functionality
      persist across various reboot types (config reload, cold, fast, warm)

Topology:
    - tgen: Requires IXIA traffic generator topology

Fixtures Used:
    - ixia_api: IXIA session for traffic generation
    - ixia_testbed_config: Testbed and port configuration
    - conn_graph_facts: DUT-to-IXIA connection topology
    - fanout_graph_facts: Fanout switch information
    - enum_dut_lossless_prio: Enumerated lossless priority for testing
    - lossless_prio_list: List of all lossless priorities
    - prio_dscp_map: Priority to DSCP mapping
    - trigger_pfcwd: Parametrized boolean for storm triggering

Dependencies:
    - files.pfcwd_basic_helper: Basic PFCWD test implementation
    - files.helper: PFCWD test skip logic and warm reboot handling
    - tests.common.reboot: Reboot utilities for different reboot types

Notes:
    - Tests both storm detection and normal operation modes
    - Validates PFCWD detects storms and initiates recovery
    - Checks dependent services (teamd, snmp, dhcp_relay, radv) after reboot
    - Warm reboot may be skipped on some platforms
    - Configuration saved before reboot tests
=============================================================================
"""
import pytest
import logging

from tests.common.helpers.assertions import pytest_require, pytest_assert
from tests.common.fixtures.conn_graph_facts import conn_graph_facts, fanout_graph_facts     # noqa: F401
from tests.common.ixia.ixia_fixtures import ixia_api_serv_ip, ixia_api_serv_port,\
    ixia_api_serv_user, ixia_api_serv_passwd, ixia_api, ixia_testbed_config                 # noqa: F401
from tests.common.ixia.qos_fixtures import prio_dscp_map, lossless_prio_list                # noqa: F401
from tests.common.reboot import reboot
from tests.common.utilities import wait_until
from tests.ixia.files.helper import skip_warm_reboot
from .files.pfcwd_basic_helper import run_pfcwd_basic_test
from .files.helper import skip_pfcwd_test

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.topology('tgen')]

DEPENDENT_SERVICES = ['teamd', 'snmp', 'dhcp_relay', 'radv']


@pytest.mark.parametrize("trigger_pfcwd", [True, False])
def test_pfcwd_basic_single_lossless_prio(ixia_api, ixia_testbed_config, conn_graph_facts,          # noqa: F811
                                          fanout_graph_facts, duthosts, rand_one_dut_hostname,      # noqa: F811
                                          rand_one_dut_portname_oper_up, enum_dut_lossless_prio,
                                          prio_dscp_map, trigger_pfcwd):                            # noqa: F811
    """
    Run PFC watchdog basic test on a single lossless priority

    Args:
        ixia_api (pytest fixture): IXIA session
        ixia_testbed_config (pytest fixture): testbed configuration information
        conn_graph_facts (pytest fixture): connection graph
        fanout_graph_facts (pytest fixture): fanout graph
        duthosts (pytest fixture): list of DUTs
        rand_one_dut_hostname (str): hostname of DUT
        rand_one_dut_portname_oper_up (str): port to test, e.g., 's6100-1|Ethernet0'
        enum_dut_lossless_prio (str): name of lossless priority to test, e.g., 's6100-1|3'
        prio_dscp_map (pytest fixture): priority vs. DSCP map (key = priority)
        trigger_pfcwd (bool): if PFC watchdog is expected to be triggered

    Returns:
        N/A
    """
    dut_hostname, dut_port = rand_one_dut_portname_oper_up.split('|')
    dut_hostname2, lossless_prio = enum_dut_lossless_prio.split('|')
    pytest_require(rand_one_dut_hostname == dut_hostname == dut_hostname2,
                   "Priority and port are not mapped to the expected DUT")

    duthost = duthosts[rand_one_dut_hostname]
    skip_pfcwd_test(duthost=duthost, trigger_pfcwd=trigger_pfcwd)

    testbed_config, port_config_list = ixia_testbed_config
    lossless_prio = int(lossless_prio)

    run_pfcwd_basic_test(api=ixia_api,
                         testbed_config=testbed_config,
                         port_config_list=port_config_list,
                         conn_data=conn_graph_facts,
                         fanout_data=fanout_graph_facts,
                         duthost=duthost,
                         dut_port=dut_port,
                         prio_list=[lossless_prio],
                         prio_dscp_map=prio_dscp_map,
                         trigger_pfcwd=trigger_pfcwd)


@pytest.mark.parametrize("trigger_pfcwd", [True, False])
def test_pfcwd_basic_multi_lossless_prio(ixia_api, ixia_testbed_config, conn_graph_facts,       # noqa: F811
                                         fanout_graph_facts, duthosts, rand_one_dut_hostname,   # noqa: F811
                                         rand_one_dut_portname_oper_up, lossless_prio_list,     # noqa: F811
                                         prio_dscp_map, trigger_pfcwd):                         # noqa: F811
    """
    Run PFC watchdog basic test on multiple lossless priorities

    Args:
        ixia_api (pytest fixture): IXIA session
        ixia_testbed_config (pytest fixture): testbed configuration information
        conn_graph_facts (pytest fixture): connection graph
        fanout_graph_facts (pytest fixture): fanout graph
        duthosts (pytest fixture): list of DUTs
        rand_one_dut_hostname (str): hostname of DUT
        rand_one_dut_portname_oper_up (str): port to test, e.g., 's6100-1|Ethernet0'
        lossless_prio_list (pytest fixture): list of all the lossless priorities
        prio_dscp_map (pytest fixture): priority vs. DSCP map (key = priority)
        trigger_pfcwd (bool): if PFC watchdog is expected to be triggered

    Returns:
        N/A
    """
    dut_hostname, dut_port = rand_one_dut_portname_oper_up.split('|')
    pytest_require(rand_one_dut_hostname == dut_hostname,
                   "Port is not mapped to the expected DUT")

    duthost = duthosts[rand_one_dut_hostname]
    skip_pfcwd_test(duthost=duthost, trigger_pfcwd=trigger_pfcwd)

    testbed_config, port_config_list = ixia_testbed_config

    run_pfcwd_basic_test(api=ixia_api,
                         testbed_config=testbed_config,
                         port_config_list=port_config_list,
                         conn_data=conn_graph_facts,
                         fanout_data=fanout_graph_facts,
                         duthost=duthost,
                         dut_port=dut_port,
                         prio_list=lossless_prio_list,
                         prio_dscp_map=prio_dscp_map,
                         trigger_pfcwd=trigger_pfcwd)


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize('reboot_type', ['warm', 'cold', 'fast'])
@pytest.mark.parametrize("trigger_pfcwd", [True, False])
def test_pfcwd_basic_single_lossless_prio_reboot(ixia_api, ixia_testbed_config, conn_graph_facts,       # noqa: F811
                                                 fanout_graph_facts, localhost, duthosts,               # noqa: F811
                                                 rand_one_dut_hostname, rand_one_dut_portname_oper_up,
                                                 rand_one_dut_lossless_prio,
                                                 prio_dscp_map, reboot_type, trigger_pfcwd):            # noqa: F811
    """
    Verify PFC watchdog basic test works on a single lossless priority after various types of reboot

    Args:
        ixia_api (pytest fixture): IXIA session
        ixia_testbed_config (pytest fixture): testbed configuration information
        conn_graph_facts (pytest fixture): connection graph
        fanout_graph_facts (pytest fixture): fanout graph
        localhost (pytest fixture): localhost handle
        duthosts (pytest fixture): list of DUTs
        rand_one_dut_hostname (str): hostname of DUT
        rand_one_dut_portname_oper_up (str): name of port to test, e.g., 's6100-1|Ethernet0'
        rand_one_dut_lossless_prio (str): name of lossless priority to test, e.g., 's6100-1|3'
        prio_dscp_map (pytest fixture): priority vs. DSCP map (key = priority)
        reboot_type (str): reboot type to be issued on the DUT
        trigger_pfcwd (bool): if PFC watchdog is expected to be triggered

    Returns:
        N/A
    """
    dut_hostname, dut_port = rand_one_dut_portname_oper_up.split('|')
    dut_hostname2, lossless_prio = rand_one_dut_lossless_prio.split('|')
    pytest_require(rand_one_dut_hostname == dut_hostname == dut_hostname2,
                   "Priority and port are not mapped to the expected DUT")

    duthost = duthosts[rand_one_dut_hostname]
    skip_pfcwd_test(duthost=duthost, trigger_pfcwd=trigger_pfcwd)
    skip_warm_reboot(duthost, reboot_type)

    testbed_config, port_config_list = ixia_testbed_config
    lossless_prio = int(lossless_prio)

    logger.info("Issuing a {} reboot on the dut {}".format(reboot_type, duthost.hostname))
    reboot(duthost, localhost, reboot_type=reboot_type)
    logger.info("Wait until the system is stable")
    pytest_assert(wait_until(300, 20, 0, duthost.critical_services_fully_started),
                  "Not all critical services are fully started")

    run_pfcwd_basic_test(api=ixia_api,
                         testbed_config=testbed_config,
                         port_config_list=port_config_list,
                         conn_data=conn_graph_facts,
                         fanout_data=fanout_graph_facts,
                         duthost=duthost,
                         dut_port=dut_port,
                         prio_list=[lossless_prio],
                         prio_dscp_map=prio_dscp_map,
                         trigger_pfcwd=trigger_pfcwd)


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize('reboot_type', ['warm', 'cold', 'fast'])
@pytest.mark.parametrize("trigger_pfcwd", [True, False])
def test_pfcwd_basic_multi_lossless_prio_reboot(ixia_api, ixia_testbed_config, conn_graph_facts,        # noqa: F811
                                                fanout_graph_facts, localhost, duthosts,                # noqa: F811
                                                rand_one_dut_hostname, rand_one_dut_portname_oper_up,
                                                lossless_prio_list, prio_dscp_map, reboot_type,         # noqa: F811
                                                trigger_pfcwd):
    """
    Verify PFC watchdog basic test works on multiple lossless priorities after various kinds of reboots

    Args:
        ixia_api (pytest fixture): IXIA session
        ixia_testbed_config (pytest fixture): testbed configuration information
        conn_graph_facts (pytest fixture): connection graph
        fanout_graph_facts (pytest fixture): fanout graph
        localhost (pytest fixture): localhost handle
        duthosts (pytest fixture): list of DUTs
        rand_one_dut_hostname (str): hostname of DUT
        rand_one_dut_portname_oper_up (str): name of port to test, e.g., 's6100-1|Ethernet0'
        lossless_prio_list (pytest fixture): list of all the lossless priorities
        prio_dscp_map (pytest fixture): priority vs. DSCP map (key = priority)
        reboot_type (str): reboot type to be issued on the DUT
        trigger_pfcwd (bool): if PFC watchdog is expected to be triggered

    Returns:
        N/A
    """
    dut_hostname, dut_port = rand_one_dut_portname_oper_up.split('|')
    pytest_require(rand_one_dut_hostname == dut_hostname,
                   "Port is not mapped to the expected DUT")

    duthost = duthosts[rand_one_dut_hostname]
    skip_pfcwd_test(duthost=duthost, trigger_pfcwd=trigger_pfcwd)
    skip_warm_reboot(duthost, reboot_type)

    testbed_config, port_config_list = ixia_testbed_config

    logger.info("Issuing a {} reboot on the dut {}".format(reboot_type, duthost.hostname))
    reboot(duthost, localhost, reboot_type=reboot_type)
    logger.info("Wait until the system is stable")
    pytest_assert(wait_until(300, 20, 0, duthost.critical_services_fully_started),
                  "Not all critical services are fully started")

    run_pfcwd_basic_test(api=ixia_api,
                         testbed_config=testbed_config,
                         port_config_list=port_config_list,
                         conn_data=conn_graph_facts,
                         fanout_data=fanout_graph_facts,
                         duthost=duthost,
                         dut_port=dut_port,
                         prio_list=lossless_prio_list,
                         prio_dscp_map=prio_dscp_map,
                         trigger_pfcwd=trigger_pfcwd)


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize('restart_service', ['swss'])
@pytest.mark.parametrize("trigger_pfcwd", [True, False])
def test_pfcwd_basic_single_lossless_prio_service_restart(ixia_api, ixia_testbed_config, conn_graph_facts,  # noqa: F811
                                                          fanout_graph_facts, duthosts,                    # noqa: F811
                                                          rand_one_dut_hostname, rand_one_dut_portname_oper_up,
                                                          rand_one_dut_lossless_prio, prio_dscp_map,        # noqa: F811
                                                          restart_service, trigger_pfcwd):
    """
    Verify PFC watchdog basic test works on a single lossless priority after various service restarts

    Args:
        ixia_api (pytest fixture): IXIA session
        ixia_testbed_config (pytest fixture): testbed configuration information
        conn_graph_facts (pytest fixture): connection graph
        fanout_graph_facts (pytest fixture): fanout graph
        duthosts (pytest fixture): list of DUTs
        rand_one_dut_hostname (str): hostname of DUT
        rand_one_dut_portname_oper_up (str): name of port to test, e.g., 's6100-1|Ethernet0'
        rand_one_dut_lossless_prio (str): name of lossless priority to test, e.g., 's6100-1|3'
        prio_dscp_map (pytest fixture): priority vs. DSCP map (key = priority)
        restart_service (str): service to restart on the DUT. Only 'swss' affects pfcwd currently
        trigger_pfcwd (bool): if PFC watchdog is expected to be triggered

    Returns:
        N/A
    """
    dut_hostname, dut_port = rand_one_dut_portname_oper_up.split('|')
    dut_hostname2, lossless_prio = rand_one_dut_lossless_prio.split('|')
    pytest_require(rand_one_dut_hostname == dut_hostname == dut_hostname2,
                   "Priority and port are not mapped to the expected DUT")

    duthost = duthosts[rand_one_dut_hostname]
    skip_pfcwd_test(duthost=duthost, trigger_pfcwd=trigger_pfcwd)

    testbed_config, port_config_list = ixia_testbed_config
    lossless_prio = int(lossless_prio)

    logger.info("Issuing a restart of service {} on the dut {}".format(restart_service, duthost.hostname))
    services_to_reset = DEPENDENT_SERVICES + [restart_service]
    for service in services_to_reset:
        duthost.command("systemctl reset-failed {}".format(service))
    duthost.command("systemctl restart {}".format(restart_service))
    logger.info("Wait until the system is stable")
    pytest_assert(wait_until(300, 20, 0, duthost.critical_services_fully_started),
                  "Not all critical services are fully started")

    run_pfcwd_basic_test(api=ixia_api,
                         testbed_config=testbed_config,
                         port_config_list=port_config_list,
                         conn_data=conn_graph_facts,
                         fanout_data=fanout_graph_facts,
                         duthost=duthost,
                         dut_port=dut_port,
                         prio_list=[lossless_prio],
                         prio_dscp_map=prio_dscp_map,
                         trigger_pfcwd=trigger_pfcwd)


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize('restart_service', ['swss'])
@pytest.mark.parametrize("trigger_pfcwd", [True, False])
def test_pfcwd_basic_multi_lossless_prio_restart_service(ixia_api, ixia_testbed_config, conn_graph_facts,   # noqa: F811
                                                         fanout_graph_facts, duthosts,                      # noqa: F811
                                                         rand_one_dut_hostname, rand_one_dut_portname_oper_up,
                                                         lossless_prio_list, prio_dscp_map,                 # noqa: F811
                                                         restart_service, trigger_pfcwd):
    """
    Verify PFC watchdog basic test works on multiple lossless priorities after various service restarts

    Args:
        ixia_api (pytest fixture): IXIA session
        ixia_testbed_config (pytest fixture): testbed configuration information
        conn_graph_facts (pytest fixture): connection graph
        fanout_graph_facts (pytest fixture): fanout graph
        duthosts (pytest fixture): list of DUTs
        rand_one_dut_hostname (str): hostname of DUT
        rand_one_dut_portname_oper_up (str): name of port to test, e.g., 's6100-1|Ethernet0'
        lossless_prio_list (pytest fixture): list of all the lossless priorities
        prio_dscp_map (pytest fixture): priority vs. DSCP map (key = priority)
        restart_service (str): service to restart on the DUT. Only 'swss' affects pfcwd currently
        trigger_pfcwd (bool): if PFC watchdog is expected to be triggered

    Returns:
        N/A
    """
    dut_hostname, dut_port = rand_one_dut_portname_oper_up.split('|')
    pytest_require(rand_one_dut_hostname == dut_hostname,
                   "Port is not mapped to the expected DUT")

    duthost = duthosts[rand_one_dut_hostname]
    skip_pfcwd_test(duthost=duthost, trigger_pfcwd=trigger_pfcwd)

    testbed_config, port_config_list = ixia_testbed_config

    logger.info("Issuing a restart of service {} on the dut {}".format(restart_service, duthost.hostname))
    services_to_reset = DEPENDENT_SERVICES + [restart_service]
    for service in services_to_reset:
        duthost.command("systemctl reset-failed {}".format(service))
    duthost.command("systemctl restart {}".format(restart_service))
    logger.info("Wait until the system is stable")
    pytest_assert(wait_until(300, 20, 0, duthost.critical_services_fully_started),
                  "Not all critical services are fully started")

    run_pfcwd_basic_test(api=ixia_api,
                         testbed_config=testbed_config,
                         port_config_list=port_config_list,
                         conn_data=conn_graph_facts,
                         fanout_data=fanout_graph_facts,
                         duthost=duthost,
                         dut_port=dut_port,
                         prio_list=lossless_prio_list,
                         prio_dscp_map=prio_dscp_map,
                         trigger_pfcwd=trigger_pfcwd)
