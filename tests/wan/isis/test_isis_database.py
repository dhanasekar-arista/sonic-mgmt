"""
=============================================================================
Module: wan/isis
File: test_isis_database.py
=============================================================================

Description:
    This test validates ISIS LSDB (Link State Database) synchronization
    between two DUT devices. It verifies that ISIS databases are properly
    synchronized and contain identical LSP entries.

Test Intent:
    - test_isis_database: Validates ISIS database integrity by comparing
      LSP entries between two connected DUT devices, ensuring databases
      are synchronized (ignoring local and holdtime fields)

Topology:
    wan-2dut (WAN topology with 2 DUTs)

Fixtures Used:
    - isis_common_setup_teardown: Sets up ISIS configuration
    - duthosts: Multi-DUT fixture

Dependencies:
    - tests.common.helpers.assertions: For pytest assertions
    - tests.common.devices.multi_asic: For multi-ASIC support
    - isis_helpers: For ISIS configuration helpers

Notes:
    - Compares LSP entries between two DUT ISIS databases
    - Ignores 'local' and 'holdtime' fields during comparison
    - Validates LSP count matches between databases
    - Ensures database synchronization is working correctly
    - Uses DEFAULT_ISIS_INSTANCE from isis_helpers
=============================================================================
"""
import time
import pytest
import logging

from tests.common.helpers.assertions import pytest_assert
from tests.common.devices.multi_asic import MultiAsicSonicHost
from isis_helpers import DEFAULT_ISIS_INSTANCE as isis_instance


logger = logging.getLogger(__name__)


pytestmark = [
    pytest.mark.topology('wan-2dut'),
]


def compare_dicts(dict1, dict2, ignore_keys=None):
    if dict1.keys() != dict2.keys():
        return False
    for key in dict1.keys():
        if ignore_keys is not None and key in ignore_keys:
            continue
        if dict1[key] != dict2[key]:
            return False
    return True


def check_isis_database_integrity(dut_database, nbr_database):
    pytest_assert(dut_database[isis_instance].keys() == nbr_database[isis_instance].keys(),
                  'IS-IS database lsp count not equal.')

    ignore_keys = ['local', 'holdtime']
    for key, _ in dut_database[isis_instance].items():
        pytest_assert(compare_dicts(dut_database[isis_instance][key],
                                    nbr_database[isis_instance][key],
                                    ignore_keys),
                      'IS-IS lsp {} is not the same.'.format(key))


def check_isis_database_detail_integrity(dut_database_detail, nbr_database_detail):
    pytest_assert(dut_database_detail[isis_instance].keys() == nbr_database_detail[isis_instance].keys(),
                  'IS-IS detailed database lsp count not equal.')

    for key, _ in dut_database_detail[isis_instance].items():
        pytest_assert(compare_dicts(dut_database_detail[isis_instance][key],
                                    nbr_database_detail[isis_instance][key]),
                      'IS-IS lsp detail {} is not the same.'.format(key))


def check_isis_route_integrity(dut_route, nbr_route):
    pytest_assert(dut_route[isis_instance].keys() == nbr_route[isis_instance].keys(),
                  'IS-IS route dict is incorrect.')
    pytest_assert(dut_route[isis_instance]['ipv4'].keys() == nbr_route[isis_instance]['ipv4'].keys(),
                  'IS-IS ipv4 route count not equal.')
    pytest_assert(dut_route[isis_instance]['ipv6'].keys() == nbr_route[isis_instance]['ipv6'].keys(),
                  'IS-IS ipv6 route count not equal.')


@pytest.mark.parametrize('check_type', ['database', 'database_detail', 'route'])
def test_isis_database_integrity(isis_common_setup_teardown, check_type):
    selected_connections = isis_common_setup_teardown

    if check_type == 'database':
        time.sleep(30)
    dut_isis_facts = nbr_isis_facts = None
    for dut_host, _, nbr_host, _ in selected_connections:
        if isinstance(dut_host, MultiAsicSonicHost) and isinstance(nbr_host, MultiAsicSonicHost):
            dut_isis_facts = dut_host.isis_facts()['ansible_facts']['isis_facts']
            nbr_isis_facts = nbr_host.isis_facts()['ansible_facts']['isis_facts']

    if dut_isis_facts is None or nbr_isis_facts is None:
        pytest.skip('Skip as no inter-connected dut interface on vtestbed')

    if check_type == 'database':
        check_isis_database_integrity(dut_isis_facts['database'], nbr_isis_facts['database'])
    elif check_type == 'database_detail':
        check_isis_database_detail_integrity(dut_isis_facts['database_detail'], nbr_isis_facts['database_detail'])
    else:
        check_isis_route_integrity(dut_isis_facts['route'], nbr_isis_facts['route'])
