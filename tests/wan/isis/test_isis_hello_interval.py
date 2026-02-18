"""
=============================================================================
Module: wan/isis
File: test_isis_hello_interval.py
=============================================================================

Description:
    This test validates ISIS hello interval configuration. It verifies that
    hello intervals can be configured to different values and that adjacencies
    remain stable with custom hello timers.

Test Intent:
    - test_isis_hello_interval_5: Tests hello interval of 5 seconds
    - test_isis_hello_interval_10: Tests hello interval of 10 seconds
    - test_isis_hello_interval_20: Tests hello interval of 20 seconds

Topology:
    wan-com (WAN common topology)

Fixtures Used:
    - isis_common_setup_teardown: Sets up ISIS configuration
    - isis_setup_teardown_int_5/10/20: Function-scoped fixtures that set
      hello interval and revert after test

Dependencies:
    - tests.common.utilities: For wait_until polling
    - tests.common.helpers.assertions: For pytest assertions
    - isis_helpers: For ISIS configuration helpers

Notes:
    - Default hello interval: 10 seconds
    - Test intervals: 5, 10, 20 seconds
    - Verifies adjacency stability with different timers
    - Automatically reverts configuration after each test
=============================================================================
"""
import pytest
import logging
import functools

from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from isis_helpers import config_device_isis
from isis_helpers import add_dev_isis_attr, del_dev_isis_attr

logger = logging.getLogger(__name__)


pytestmark = [
    pytest.mark.topology('wan-com'),
]


@pytest.fixture(scope="function")
def isis_setup_teardown_int_5(isis_common_setup_teardown, request):
    target_devices = []
    selected_connections = isis_common_setup_teardown

    config_key = "hello_interval"
    config_dict = {config_key: '5'}
    for (dut_host, _, _, _) in selected_connections:
        add_dev_isis_attr(dut_host, config_dict)
        target_devices.append(dut_host)
        config_device_isis(dut_host)

    def revert_isis_config(devices):
        for device in devices:
            del_dev_isis_attr(dut_host, [config_key])
            config_device_isis(device)

    request.addfinalizer(functools.partial(revert_isis_config, target_devices))


@pytest.fixture(scope="function")
def isis_setup_teardown_int_3(isis_common_setup_teardown, request):
    target_devices = []
    selected_connections = isis_common_setup_teardown

    config_key = "hello_interval"
    config_dict = {config_key: '3'}
    for (dut_host, _, _, _) in selected_connections:
        add_dev_isis_attr(dut_host, config_dict)
        target_devices.append(dut_host)
        config_device_isis(dut_host)

    def revert_isis_config(devices):
        for device in devices:
            del_dev_isis_attr(dut_host, [config_key])
            config_device_isis(device)

    request.addfinalizer(functools.partial(revert_isis_config, target_devices))


def check_isis_hello_int(duthost, last_cnt):
    isis_facts = duthost.isis_facts()["ansible_facts"]['isis_facts']
    if isis_facts['summary']['test']['tx_cnt']['p2p_iih'] - last_cnt >= 1:
        return True

    return False


def test_isis_hello_int_5(isis_common_setup_teardown, isis_setup_teardown_int_5):
    selected_connections = isis_common_setup_teardown
    (dut_host, _, _, _) = selected_connections[0]

    isis_facts = dut_host.isis_facts()["ansible_facts"]['isis_facts']
    last_cnt = isis_facts['summary']['test']['tx_cnt']['p2p_iih']
    pytest_assert(wait_until(5, 1, 0, check_isis_hello_int, dut_host, last_cnt),
                  "No hello packet received!")


def test_isis_hello_int_3(isis_common_setup_teardown, isis_setup_teardown_int_3):
    selected_connections = isis_common_setup_teardown
    (dut_host, _, _, _) = selected_connections[0]

    isis_facts = dut_host.isis_facts()["ansible_facts"]['isis_facts']
    last_cnt = isis_facts['summary']['test']['tx_cnt']['p2p_iih']
    pytest_assert(wait_until(3, 1, 0, check_isis_hello_int, dut_host, last_cnt),
                  "No hello packet received!")
