"""
=============================================================================
Module: k8s
File: test_disable_flag.py
=============================================================================

Description:
    This test module validates the Kubernetes server disable flag functionality
    in SONiC. It tests the ability to enable/disable DUT connection to
    Kubernetes master and verifies proper state transitions.

Test Intent:
    - test_disable_flag: Validates that the kube server disable flag correctly
      controls DUT connection to Kubernetes master, testing transitions from
      connected -> disabled -> enabled states and verifying state changes

Topology:
    - any: Works with any topology

Fixtures Used:
    - duthost: DUT host object for configuration
    - k8scluster: Kubernetes cluster fixture providing master VIP

Dependencies:
    - k8s_test_utilities: Kubernetes test helper functions
    - tests.common.helpers.assertions: Test assertion utilities

Notes:
    - Tests 'config kube server disable on/off' commands
    - Validates server connection status changes appropriately
    - Uses polling to wait for status transitions
    - Ensures DUT properly disconnects when disabled
    - Verifies automatic reconnection when re-enabled
=============================================================================
"""
import pytest
import k8s_test_utilities as ku

from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.topology('any')
]


def test_disable_flag(duthost, k8scluster):
    """
    Test case to ensure that kube server disable flag works as expected when toggled

    Joins master to set baseline state (disable=false, joined to master)

    Set disable=true, ensure DUT resets from master

    Set disable=false, ensure DUT joins master

    Args:
        duthost: DUT host object
        k8scluster: shortcut fixture for getting cluster of Kubernetes master hosts
    """
    ku.join_master(duthost, k8scluster.vip)

    duthost.shell('sudo config kube server disable on')
    server_connect_exp_status = False
    server_connect_act_status = ku.check_connected(duthost)
    server_connect_status_updated = ku.poll_for_status_change(duthost, server_connect_exp_status)
    pytest_assert(server_connect_status_updated, "Test disable flag failed, Expected server connected status: {}, "
                  "Found server connected status: {}".format(server_connect_exp_status, server_connect_act_status))

    duthost.shell('sudo config kube server disable off')
    server_connect_exp_status = True
    server_connect_act_status = ku.check_connected(duthost)
    server_connect_status_updated = ku.poll_for_status_change(duthost, server_connect_exp_status)
    pytest_assert(server_connect_status_updated, "Test disable flag failed, Expected server connected status: {}, "
                  "Found server connected status: {}".format(server_connect_exp_status, server_connect_act_status))
