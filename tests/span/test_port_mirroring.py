"""
=============================================================================
Module: span
File: test_port_mirroring.py
=============================================================================

Description:
    This test module validates local port mirroring (SPAN) functionality on
    SONiC switches. It tests ingress, egress, and bidirectional mirroring
    sessions, verifying that traffic is correctly copied to monitor ports
    for traffic analysis and troubleshooting purposes.

Test Intent:
    - test_mirroring_rx: Validates ingress (RX) direction port mirroring by
      sending packets to DUT and verifying they are mirrored to monitor port
    - test_mirroring_tx: Tests egress (TX) direction port mirroring by sending
      packets from DUT and confirming mirror copies reach monitor port
    - test_mirroring_both: Verifies bidirectional mirroring (both RX and TX)
      correctly mirrors traffic in both directions to monitor port

Topology:
    - Supported: t0 topology
    - Requires source ports and dedicated monitor/destination port
    - PTF used for packet injection and verification

Fixtures Used:
    - ptfadapter: PTF adapter for packet transmission and reception
    - setup_session: Configures SPAN session with source and destination ports
    - change_mac_addresses: PTF host MAC address configuration

Dependencies:
    - span_helpers: Helper functions for sending and verifying mirrored packets
    - tests.common.fixtures.ptfhost_utils: PTF host utilities

Notes:
    - SPAN session configured with source and monitor ports via fixture
    - Test uses ICMP packets for mirroring verification
    - Ingress test: packets sent TO DUT (source1 -> destination)
    - Egress test: packets sent FROM DUT (source2 -> destination)
    - Bidirectional test: validates both ingress and egress mirroring
    - Monitor port receives copies of original packets
    - Mirrored packets retain original headers and content
    - Tests verify packet arrival on monitor port within timeout
    - Session cleanup handled by fixture teardown
=============================================================================
"""

import pytest

from tests.common.fixtures.ptfhost_utils import change_mac_addresses    # noqa F401
from span_helpers import send_and_verify_mirrored_packet

pytestmark = [
    pytest.mark.topology('t0')
]


def test_mirroring_rx(ptfadapter, setup_session):
    '''
    Test case #1
    Verify ingress direction session

    Steps:
        1. Create ICMP packet
        2. Send packet from PTF to DUT
        3. Verify that packet is mirrored to monitor port

    Pass Criteria: PTF gets ICMP packet on monitor port.
    '''
    send_and_verify_mirrored_packet(ptfadapter,
                                    setup_session['source1_index'],
                                    setup_session['destination_index'])


def test_mirroring_tx(ptfadapter, setup_session):
    '''
    Test case #2
    Verify egress direction session

    Steps:
        1. Create ICMP packet
        2. Send packet from DUT to PTF
        3. Verify that packet is mirrored to monitor port

    Pass Criteria: PTF gets ICMP packet on monitor port.
    '''
    send_and_verify_mirrored_packet(ptfadapter,
                                    setup_session['source2_index'],
                                    setup_session['destination_index'])


def test_mirroring_both(ptfadapter, setup_session):
    '''
    Test case #3
    Verify bidirectional session

    Steps:
        1. Create ICMP packet
        2. Send packet from PTF to DUT
        3. Verify that packet is mirrored to monitor port
        4. Create ICMP packet
        5. Send packet from DUT to PTF
        6. Verify that packet is mirrored to monitor port

    Pass Criteria: PTF gets both ICMP packets on monitor port.
    '''
    send_and_verify_mirrored_packet(ptfadapter,
                                    setup_session['source1_index'],
                                    setup_session['destination_index'])

    send_and_verify_mirrored_packet(ptfadapter,
                                    setup_session['source2_index'],
                                    setup_session['destination_index'])


def test_mirroring_multiple_source(ptfadapter, setup_session):
    '''
    Test case #4
    Verify ingress direction session with multiple source ports

    Steps:
        1. Create ICMP packet
        2. Send packet from PTF to first source port on DUT
        3. Verify that packet is mirrored to monitor port
        4. Create ICMP packet
        5. Send packet from PTF to second source port on DUT
        6. Verify that packet is mirrored to monitor port

    Pass Criteria: PTF gets both ICMP packets on monitor port.
    '''
    send_and_verify_mirrored_packet(ptfadapter,
                                    setup_session['source1_index'],
                                    setup_session['destination_index'])

    send_and_verify_mirrored_packet(ptfadapter,
                                    setup_session['source2_index'],
                                    setup_session['destination_index'])
