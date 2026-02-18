"""
=============================================================================
Module: ipfwd
File: test_mtu.py
=============================================================================

Description:
    This test module validates MTU (Maximum Transmission Unit) handling in
    SONiC IP forwarding. It tests packet forwarding for different MTU sizes,
    ensuring packets are properly forwarded or fragmented based on configured
    MTU values.

Test Intent:
    - test_mtu: Parametrized test that validates IP forwarding with MTU sizes
      of 1514 bytes (standard) and 9114 bytes (jumbo frames), ensuring packets
      within MTU are forwarded and oversized packets are handled correctly

Topology:
    - t1, t2, m1, lt2, ft2: Tests run on T1 and related topologies

Fixtures Used:
    - copy_ptftests_directory: Copies PTF test files to PTF host
    - set_ptf_port_mapping_mode: Configures PTF port mapping mode
    - gather_facts: Provides router MAC, IPs, and port information
    - tbinfo: Testbed topology information

Dependencies:
    - tests.ptf_runner: PTF test execution framework
    - tests.common.fixtures.ptfhost_utils: PTF configuration utilities

Notes:
    - Test is parametrized to run with MTU values: 1514 and 9114 bytes
    - Only runs on virtual switch (vs) device types
    - Tests both IPv4 and IPv6 packet forwarding with different MTU sizes
    - PTF test verifies packets are forwarded when size <= MTU
    - KVM support is enabled for virtual environment testing
    - Log files generated with timestamp in /tmp/mtu_test.<mtu>-<timestamp>.log
=============================================================================
"""
import pytest
import logging

from tests.common.fixtures.ptfhost_utils import copy_ptftests_directory     # noqa: F401
from tests.common.fixtures.ptfhost_utils import set_ptf_port_mapping_mode   # noqa: F401
from tests.ptf_runner import ptf_runner
from datetime import datetime

pytestmark = [
    pytest.mark.topology('t1', 't2', 'm1', 'lt2', 'ft2'),
    pytest.mark.device_type('vs')
]


@pytest.mark.parametrize("mtu", [1514, 9114])
def test_mtu(tbinfo, ptfhost, mtu, gather_facts):

    testbed_type = tbinfo['topo']['name']

    log_file = "/tmp/mtu_test.{}-{}.log".format(mtu, datetime.now().strftime('%Y-%m-%d-%H:%M:%S'))

    logging.info("Starting MTU test. PTF log file: %s" % log_file)

    ptf_runner(ptfhost,
               "ptftests",
               "mtu_test.MtuTest",
               platform_dir="ptftests",
               params={"testbed_type": testbed_type,
                       "router_mac": gather_facts['src_router_mac'],
                       "testbed_mtu": mtu,
                       "src_host_ip": gather_facts.get('src_host_ipv4'),
                       "src_router_ip": gather_facts.get('src_router_ipv4'),
                       "dst_host_ip": gather_facts.get('dst_host_ipv4'),
                       "src_host_ipv6": gather_facts.get('src_host_ipv6'),
                       "src_router_ipv6": gather_facts.get('src_router_ipv6'),
                       "dst_host_ipv6": gather_facts.get('dst_host_ipv6'),
                       "src_ptf_port_list": gather_facts.get('src_port_ids'),
                       "dst_ptf_port_list": gather_facts.get('dst_port_ids'),
                       "kvm_support": True
                       },
               log_file=log_file,
               socket_recv_size=16384,
               is_python3=True)
