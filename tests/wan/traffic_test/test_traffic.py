"""
=============================================================================
Module: wan/traffic_test
File: test_traffic.py
=============================================================================

Description:
    Validates traffic forwarding in WAN topologies using TRex traffic generator.
    Tests IMIX traffic patterns and validates throughput.

Test Intent:
    - test_traffic: Validates traffic forwarding using TRex generator with
      IMIX (Internet Mix) traffic patterns

Topology:
    wan-3link-tg (vs devices with TRex traffic generator)

Dependencies:
    - subprocess: For running TRex commands
    - TRex: Traffic generator in Docker container

Notes:
    - Uses TRex v2.41
    - Runs stl_imix.py script for IMIX traffic
    - Validates packet forwarding and statistics
    - Traffic generator runs in Docker container
=============================================================================
"""
import logging
import pytest
import subprocess

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('wan-3link-tg'),
    pytest.mark.device_type('vs')
]


def start_traffic():

    result = dict()
    process = subprocess.Popen(['docker', 'exec',
                                'trex', 'sh', '-c',
                                'python /var/trex/v2.41/trex_client/stl/examples/stl_imix.py'],
                               stdout=subprocess.PIPE,
                               universal_newlines=True)
    while True:
        output = process.stdout.readline()
        if not output:
            break
        out = output.strip().split(':')
        result[out[0]] = out[1]

        return_code = process.poll()
        if return_code is not None:
            break

    return result


def test_traffic():

    output = start_traffic()

    assert int(output['lost']) <= 0, "Packets lost happen!"
