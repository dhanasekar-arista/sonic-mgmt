"""
Module: tests.dash
File: test_dash_acl.py
Description:
    DASH ACL (Access Control List) test suite for DPU topology. This module provides
    comprehensive testing of DASH ACL functionality including field matching, multi-stage
    ACLs, IP tag-based ACLs, and special TCP RST handling on connection table misses.

Test Intent:
    - Validate ACL field matching (src/dst IP, ports, protocol)
    - Test multi-stage ACL processing and rule priorities
    - Verify IP tag-based ACL functionality (single and multiple tags)
    - Test ACL tag ordering and priority handling
    - Validate dynamic tag updates (IP add/remove from tags)
    - Test ACL tag scale with large tag sets
    - Verify handling of non-existent tags
    - Validate TCP RST behavior on connection table miss with ACL permit/deny

Topology:
    - dpu: DPU topology for DASH testing
    - Requires DASH configuration applied via fixtures
    - Traffic flows through DPU ACL pipeline

Fixtures Used:
    - ptfadapter: PTF adapter for packet injection/verification
    - skip_dataplane_checking: Flag to skip dataplane verification
    - acl_fields_test: Fixture providing ACL field test configuration
    - acl_multi_stage_test: Fixture for multi-stage ACL testing
    - acl_tag_test: Fixture for single IP tag ACL testing
    - acl_multi_tag_test: Fixture for multiple IP tag ACL testing
    - acl_tag_order_test: Fixture for tag priority order testing
    - acl_multi_tag_order_test: Fixture for multi-tag order testing
    - acl_tag_update_ip_test: Fixture for dynamic IP add to tag testing
    - acl_tag_remove_ip_test: Fixture for dynamic IP remove from tag testing
    - acl_tag_scale_test: Fixture for tag scale testing
    - acl_tag_not_exists_test: Fixture for non-existent tag testing
    - acl_tcp_rst_test: Fixture for TCP RST on CT miss testing

Dependencies:
    - dash_acl: DASH ACL helper module with test fixtures and dataplane checkers
    - ptf.testutils: PTF packet testing utilities
    - pytest: Testing framework

Notes:
    - All ACL fixtures are defined in dash_acl module and imported here
    - Tests use check_dataplane() for packet verification (except TCP RST test)
    - TCP RST test uses check_tcp_rst_dataplane() for special validation
    - Dataplane checking can be skipped via --skip_dataplane_checking flag
    - TCP RST test validates two scenarios on NVIDIA DPU:
      1. CT miss + No SYN packet (ACK) + ACL permit -> packet forwarded
      2. CT miss + No SYN packet (ACK) + ACL deny -> packet dropped + RST sent
    - ACL rules include src IP, dst IP, src port, dst port, protocol matching
    - Tag tests validate dynamic tag membership and priority ordering
    - Scale test ensures ACL performance with large tag sets

Git History (last 5 commits):
    dab77c420 Remove TACACS fixture from none TACACS test cases (#13422)
    07f328770 Enable TACACS on test cases. (#12433)
    7834ebaea [Mellanox] Add dash tcp rst test for DPU (#12609)
    d6bf2ae8e [DASH] New test cases for dash acl tag (#11559)
    d7371c53c [dash]: Add test cases for DASH ACL (#7848)
"""

import time
import logging
import pytest
import ptf.testutils as testutils

from dash_acl import check_dataplane, acl_fields_test, acl_multi_stage_test, check_tcp_rst_dataplane, acl_tcp_rst_test # noqa: F401
from dash_acl import acl_tag_test, acl_multi_tag_test, acl_tag_order_test, acl_multi_tag_order_test  # noqa: F401
from dash_acl import acl_tag_update_ip_test, acl_tag_remove_ip_test, acl_tag_scale_test, acl_tag_not_exists_test  # noqa: F401

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('dpu'),
]


# flake8: noqa: F811
def test_acl_fields(
        ptfadapter,
        acl_fields_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_fields_test)


# flake8: noqa: F811
def test_acl_multi_stage(
        ptfadapter,
        acl_multi_stage_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_multi_stage_test)


# flake8: noqa: F811
def test_acl_tag(
        ptfadapter,
        acl_tag_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_tag_test)


# flake8: noqa: F811
def test_acl_multi_tag(
        ptfadapter,
        acl_multi_tag_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_multi_tag_test)


# flake8: noqa: F811
def test_acl_tag_not_exists(
        ptfadapter,
        acl_tag_not_exists_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_tag_not_exists_test)


# flake8: noqa: F811
def test_acl_tag_order(
        ptfadapter,
        acl_tag_order_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_tag_order_test)


# flake8: noqa: F811
def test_acl_multi_tag_order(
        ptfadapter,
        acl_multi_tag_order_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_multi_tag_order_test)


# flake8: noqa: F811
def test_acl_tag_update_ip(
        ptfadapter,
        acl_tag_update_ip_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_tag_update_ip_test)


# flake8: noqa: F811
def test_acl_tag_remove_ip(
        ptfadapter,
        acl_tag_remove_ip_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_tag_remove_ip_test)


# flake8: noqa: F811
def test_acl_tag_scale(
        ptfadapter,
        acl_tag_scale_test,
        skip_dataplane_checking
        ):
    if skip_dataplane_checking:
        return
    check_dataplane(ptfadapter, acl_tag_scale_test)


def test_acl_tcp_rst(
        ptfadapter,
        acl_tcp_rst_test
        ):
    """
    This case is to verify the two following scenarios when CT miss for TCP packet on Nvidia dpu
    1. CT miss +  No SYN packet(ACK) + ACL permit
    2. CT miss +  No SYN packet(ACK) + ACL deny
    Test steps:
    1. configure ACL permit for src:11.1.1.1/32, dst:20.2.2.2/32, src_port: 24563, dst_port: 80, protocol: tcp
    2. configure ACL deny for src:20.2.2.2/32, dst:11.1.1.1/32, src_port: 80, dst_port: 24563, protocol: tcp
    3. Send no SYN packet(ACK) matching ACL permit
    4. Check the TCP packet will be forwarded to the correct port
    5. Send no SYN packet(ACK) matching ACL Deny
    6. Check the TCP packet will be dropped, and the RST packet will be sent to the two ends
    """
    check_tcp_rst_dataplane(ptfadapter, acl_tcp_rst_test)
