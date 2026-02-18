"""
=============================================================================
Module: ecmp.inner_hashing
File: test_wr_inner_hashing.py
=============================================================================

Description:
    Test suite for validating inner packet hashing during warm reboot. This module tests
    that dynamic PBH (Policy-Based Hashing) configuration maintains inner hash behavior
    across warm reboots, ensuring traffic distribution based on encapsulated packet headers
    (VXLAN, NVGRE, IP-in-IP) continues uninterrupted during warm reboot scenarios.

Test Intent:
    - test_inner_hashing: Verify inner packet hashing works correctly during warm reboot with dynamic PBH configuration

Topology:
    - t0: Standard T0 leaf-spine topology

Fixtures Used:
    - duthost: DUT host object
    - ptfhost: PTF host for traffic generation
    - hash_keys: Hash field configuration for inner packets
    - outer_ipver: Outer IP version (ipv4/ipv6) parametrized
    - inner_ipver: Inner IP version (ipv4/ipv6) parametrized
    - router_mac: DUT router MAC address
    - vlan_ptf_ports: VLAN member ports on PTF
    - symmetric_hashing: Symmetric hash enable/disable
    - localhost: Localhost object for warm reboot
    - lag_mem_ptf_ports_groups: LAG member port groups
    - get_function_completeness_level: Test completeness level (debug/thorough)
    - setup_dynamic_pbh: Module-level fixture to configure dynamic PBH

Dependencies:
    - PTF framework for traffic generation
    - inner_hash_test.InnerHashTest PTF test module
    - PBH (Policy-Based Hashing) configuration
    - Warm reboot capability
    - VXLAN/NVGRE/IP-in-IP encapsulation support

Notes:
    - Test is marked with @pytest.mark.dynamic_config
    - Test is marked with pytest.mark.disable_loganalyzer
    - Test runs PTF inner hash test in parallel with warm reboot
    - Outer encapsulation formats: VXLAN, NVGRE, IP-in-IP
    - Random encapsulation format selected to reduce test time
    - Test completeness levels: debug (50 iterations), thorough (200 iterations)
    - VXLAN port: 13330, NVGRE TNI: 0x4000
    - PTF queue length: 1000 (PTF_QLEN)
    - Test validates hash distribution during and after warm reboot
    - Symmetric hashing: Hash same for bidirectional flows if enabled
    - Balancing test times configurable based on completeness level

=============================================================================
"""

import logging
import threading
import pytest
import random
import allure

from datetime import datetime
from tests.common import reboot
from tests.ecmp.inner_hashing.conftest import get_src_dst_ip_range, FIB_INFO_FILE_DST, VXLAN_PORT,\
    PTF_QLEN, OUTER_ENCAP_FORMATS, NVGRE_TNI, config_pbh
from tests.ptf_runner import ptf_runner

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology('t0')
]


@pytest.mark.dynamic_config
class TestWRDynamicInnerHashing():

    @pytest.fixture(scope="module", autouse=True)
    def setup_dynamic_pbh(self, duthost, vlan_ptf_ports, tbinfo):
        with allure.step('Config Dynamic PBH'):
            config_pbh(duthost, vlan_ptf_ports, tbinfo)

    def test_inner_hashing(self, duthost, hash_keys, ptfhost, outer_ipver, inner_ipver, router_mac,
                           vlan_ptf_ports, symmetric_hashing, localhost, lag_mem_ptf_ports_groups,
                           get_function_completeness_level):
        logging.info("Executing warm boot dynamic inner hash test for outer {} and inner {} with symmetric_hashing"
                     " set to {}".format(outer_ipver, inner_ipver, str(symmetric_hashing)))
        with allure.step('Run ptf test InnerHashTest and warm-reboot in parallel'):
            timestamp = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
            log_file = "/tmp/wr_inner_hash_test.DynamicInnerHashTest.{}.{}.{}.log"\
                       .format(outer_ipver, inner_ipver, timestamp)
            logging.info("PTF log file: %s" % log_file)

            # to reduce test run time, check one of encapsulation formats
            outer_encap_format = random.choice(OUTER_ENCAP_FORMATS).split()
            logging.info("Tested encapsulation format: {}".format(outer_encap_format[0]))

            outer_src_ip_range, outer_dst_ip_range = get_src_dst_ip_range(outer_ipver)
            inner_src_ip_range, inner_dst_ip_range = get_src_dst_ip_range(inner_ipver)

            normalize_level = get_function_completeness_level if get_function_completeness_level else 'debug'

            if normalize_level == 'thorough':
                balancing_test_times = 200
                balancing_range = 0.3
            else:
                balancing_test_times = 100
                balancing_range = 0.3

            reboot_thr = threading.Thread(target=reboot, args=(duthost, localhost, 'warm', 10, 0, 0, True, True,))
            reboot_thr.start()

            ptf_runner(ptfhost,
                       "ptftests",
                       "inner_hash_test.InnerHashTest",
                       platform_dir="ptftests",
                       params={"fib_info": FIB_INFO_FILE_DST,
                               "router_mac": router_mac,
                               "src_ports": vlan_ptf_ports,
                               "exp_port_groups": lag_mem_ptf_ports_groups,
                               "hash_keys": hash_keys,
                               "vxlan_port": VXLAN_PORT,
                               "inner_src_ip_range": ",".join(inner_src_ip_range),
                               "inner_dst_ip_range": ",".join(inner_dst_ip_range),
                               "outer_src_ip_range": ",".join(outer_src_ip_range),
                               "outer_dst_ip_range": ",".join(outer_dst_ip_range),
                               "balancing_test_times": balancing_test_times,
                               "balancing_range": balancing_range,
                               "outer_encap_formats": outer_encap_format,
                               "nvgre_tni": NVGRE_TNI,
                               "symmetric_hashing": symmetric_hashing},
                       log_file=log_file,
                       qlen=PTF_QLEN,
                       socket_recv_size=16384,
                       is_python3=True)
            reboot_thr.join()


@pytest.mark.static_config
class TestWRStaticInnerHashing():

    def test_inner_hashing(self, duthost, hash_keys, ptfhost, outer_ipver, inner_ipver, router_mac,
                           vlan_ptf_ports, symmetric_hashing, localhost, lag_mem_ptf_ports_groups):
        logging.info("Executing static inner hash test for outer {} and inner {} with symmetric_hashing set to {}"
                     .format(outer_ipver, inner_ipver, str(symmetric_hashing)))
        timestamp = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
        log_file = "/tmp/wr_inner_hash_test.StaticInnerHashTest.{}.{}.{}.log"\
                   .format(outer_ipver, inner_ipver, timestamp)
        logging.info("PTF log file: %s" % log_file)

        outer_src_ip_range, outer_dst_ip_range = get_src_dst_ip_range(outer_ipver)
        inner_src_ip_range, inner_dst_ip_range = get_src_dst_ip_range(inner_ipver)

        reboot_thr = threading.Thread(target=reboot, args=(duthost, localhost, 'warm', 10, 0, 0, True, True,))
        reboot_thr.start()

        ptf_runner(ptfhost,
                   "ptftests",
                   "inner_hash_test.InnerHashTest",
                   platform_dir="ptftests",
                   params={"fib_info": FIB_INFO_FILE_DST,
                           "router_mac": router_mac,
                           "src_ports": vlan_ptf_ports,
                           "exp_port_groups": lag_mem_ptf_ports_groups,
                           "hash_keys": hash_keys,
                           "vxlan_port": VXLAN_PORT,
                           "inner_src_ip_range": ",".join(inner_src_ip_range),
                           "inner_dst_ip_range": ",".join(inner_dst_ip_range),
                           "outer_src_ip_range": ",".join(outer_src_ip_range),
                           "outer_dst_ip_range": ",".join(outer_dst_ip_range),
                           "outer_encap_formats": OUTER_ENCAP_FORMATS,
                           "symmetric_hashing": symmetric_hashing},
                   log_file=log_file,
                   qlen=PTF_QLEN,
                   socket_recv_size=16384,
                   is_python3=True)
        reboot_thr.join()
