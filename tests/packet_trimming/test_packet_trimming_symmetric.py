"""
=============================================================================
Module: packet_trimming
File: test_packet_trimming_symmetric.py
=============================================================================

Description:
    This test suite validates packet trimming functionality in symmetric DSCP mode.
    Packet trimming reduces packet sizes at egress to optimize bandwidth usage while
    preserving headers and critical information. In symmetric mode, all egress ports
    use the same DSCP value for trimmed packets. Tests verify configuration validation
    and inherit traffic verification tests from the base class.

Test Intent:
    - test_trimming_configuration: Verify valid and invalid trimming configuration parameters (size, DSCP, queue)
    - Inherited tests from BasePacketTrimming: Packet size verification, buffer profile operations, ACL rule functionality, SRv6 compatibility

Topology:
    t0, t1 - Requires T0 or T1 topology

Fixtures Used:
    - duthost: Device under test host object
    - ptfadapter: PTF adapter for packet injection and verification
    - test_params: Test parameters including ingress/egress ports, buffer profiles, queues

Dependencies:
    - tests.packet_trimming.base_packet_trimming: Base class with common packet trimming test methods
    - tests.packet_trimming.packet_trimming_config: Configuration constants and helpers
    - tests.packet_trimming.packet_trimming_helper: Helper functions for trimming configuration and verification

Notes:
    - Symmetric mode uses a single DSCP value for all trimmed packets regardless of egress port
    - Trimming configuration includes: size (bytes to trim to), queue (which queue to trim), DSCP (marking value)
    - Valid configurations are derived from platform-specific capabilities
    - Invalid configurations test error handling (out of range values, unsupported combinations)
    - Inherits traffic tests from BasePacketTrimming for packet size, buffer profile, ACL, and SRv6 scenarios
=============================================================================
"""
import pytest
import logging
from tests.common.helpers.assertions import pytest_assert
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.packet_trimming.base_packet_trimming import BasePacketTrimming
from tests.packet_trimming.packet_trimming_config import PacketTrimmingConfig
from tests.packet_trimming.packet_trimming_helper import configure_trimming_global

pytestmark = [
    pytest.mark.topology("t0", "t1")
]

logger = logging.getLogger(__name__)


class TestPacketTrimmingSymmetric(BasePacketTrimming):
    trimming_mode = "symmetric"

    def configure_trimming_global_by_mode(self, duthost, size=None):
        """
        Configure trimming global by trimming mode
        """
        if size is None:
            size = PacketTrimmingConfig.get_trim_size(duthost)
        queue = PacketTrimmingConfig.get_trim_queue(duthost)
        dscp = PacketTrimmingConfig.DSCP
        configure_trimming_global(duthost, size=size, queue=queue, dscp=dscp)

    def get_extra_trimmed_packet_kwargs(self):
        return dict(
            recv_pkt_dscp_port1=PacketTrimmingConfig.DSCP,
            recv_pkt_dscp_port2=PacketTrimmingConfig.DSCP
        )

    def get_srv6_recv_pkt_dscp(self):
        return PacketTrimmingConfig.DSCP

    def test_trimming_configuration(self, duthost, test_params):
        """
        Test Case: Verify Trimming Configuration
        """
        with allure.step(f"Testing {self.trimming_mode} DSCP valid configurations"):
            for size, dscp, queue in PacketTrimmingConfig.get_valid_trim_configs(duthost):
                logger.info(f"Testing valid config: size={size}, dscp={dscp}, queue={queue}")
                pytest_assert(configure_trimming_global(duthost, size=size, queue=queue, dscp=dscp))

        with allure.step(f"Testing {self.trimming_mode} DSCP invalid configurations"):
            for size, dscp, queue in PacketTrimmingConfig.get_invalid_trim_configs(duthost):
                logger.info(f"Testing invalid config: size={size}, dscp={dscp}, queue={queue}")
                pytest_assert(not configure_trimming_global(duthost, size=size, queue=queue, dscp=dscp))
