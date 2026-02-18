"""
=============================================================================
Module: bgp
File: test_bgp_bounce.py
=============================================================================

Description:
    Tests BGP no-export community attribute functionality in SONiC. Verifies
    that routes tagged with no-export community are properly handled and not
    propagated beyond immediate peers as per RFC 1997.

Test Intent:
    - test_bgp_bounce: Validates BGP no-export community behavior by applying
      plain BGP config (without no-export) and verifying routes don't have
      the attribute, then applying no-export config and confirming routes
      are tagged correctly on ToR VMs

Topology:
    t1

Fixtures Used:
    - deploy_plain_bgp_config: Deploys standard BGP configuration
    - deploy_no_export_bgp_config: Deploys BGP config with no-export community
    - backup_bgp_config: Backs up and restores default BGP configuration
    - nbrhosts: Neighbor hosts (ToR VMs)
    - tbinfo: Testbed information

Dependencies:
    - bgp_helpers: BGP configuration and validation utilities
    - tests.common.helpers.assertions.pytest_assert
    - tests.common.utilities.is_ipv6_only_topology

Notes:
    - Tests no-export community for both IPv4 and IPv6
    - Randomly selects a ToR VM for validation
    - Waits BGP_ANNOUNCE_TIME for route propagation
    - Restores default BGP configuration after test completion
=============================================================================
"""

import random
import pytest
import time

from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import is_ipv6_only_topology
from bgp_helpers import apply_bgp_config
from bgp_helpers import get_no_export_output
from bgp_helpers import BGP_ANNOUNCE_TIME

pytestmark = [
    pytest.mark.topology('t1')
]


def test_bgp_bounce(duthost, nbrhosts, tbinfo, deploy_plain_bgp_config, deploy_no_export_bgp_config,
                    backup_bgp_config):
    """
    Verify bgp community no export functionality

    Test steps:
        1.) Generate bgp plain config
        2.) Generate bgp no export config
        3.) Apply bgp plain config
        4.) Get no export routes on one of the ToR VM
        5.) Apply bgp no export config
        6.) Get no export routes on one of the ToR VM
        7.) Apply default bgp config

    Pass Criteria: After applying bgp no export config ToR VM gets no export routes
    """
    bgp_plain_config = deploy_plain_bgp_config
    bgp_no_export_config = deploy_no_export_bgp_config

    # Check if this is an IPv6-only topology
    is_v6_topo = is_ipv6_only_topology(tbinfo)

    # Get random ToR VM
    vm_name = random.choice([vm_name for vm_name in list(nbrhosts.keys()) if vm_name.endswith('T0')])
    vm_host = nbrhosts[vm_name]['host']

    # Start all bgp sessions
    duthost.shell('config bgp startup all')

    # Apply bgp plain config
    apply_bgp_config(duthost, bgp_plain_config)

    # Give additional delay for routes to be propagated
    time.sleep(BGP_ANNOUNCE_TIME)

    # Take action on one of the ToR VM
    no_export_route_num = get_no_export_output(vm_host, ipv6=is_v6_topo)
    pytest_assert(not no_export_route_num, "Routes has no_export attribute")

    # Apply bgp no export config
    apply_bgp_config(duthost, bgp_no_export_config)

    # Give additional delay for routes to be propagated
    time.sleep(BGP_ANNOUNCE_TIME)

    # Take action on one of the ToR VM
    no_export_route_num = get_no_export_output(vm_host, ipv6=is_v6_topo)
    pytest_assert(no_export_route_num, "Routes received on T1 are no-export")
