"""
=============================================================================
Module: macsec
File: test_interop_wan_isis.py
=============================================================================

Description:
    This test validates MACsec interoperability with IS-IS (Intermediate
    System to Intermediate System) routing protocol on WAN topologies. It
    ensures that IS-IS adjacencies remain stable when MACsec is enabled,
    disabled, and re-enabled on links.

Test Intent:
    - test_isis_over_macsec: Validates IS-IS protocol functionality over
      MACsec-protected WAN links. Tests three scenarios:
      1) Verifies IS-IS neighbors are Up with MACsec enabled initially
      2) Disables MACsec on both DUT and neighbor, waits for MACsec to be
         down, then verifies IS-IS neighbors remain Up without encryption
      3) Re-enables MACsec on both ends, waits for MACsec session to
         establish, then verifies IS-IS neighbors remain Up with encryption
      Ensures IS-IS routing is resilient to MACsec state changes and that
      MACsec encryption does not break IS-IS adjacencies. Only runs on
      wan-pub-isis virtual testbed topology.

Topology:
    wan-pub-isis topology with MACsec support required

Fixtures Used:
    - tbinfo: Testbed information used to verify topology is wan-pub-isis
    - duthost: DUT host object for test execution
    - ctrl_links: Dictionary of MACsec-controlled links on the DUT
    - upstream_links: Upstream link information (parameter present but not used)
    - profile_name: MACsec profile name for re-enabling MACsec
    - wait_mka_establish: Waits for MKA session establishment before tests

Dependencies:
    - tests.common.utilities: For wait_until polling functionality
    - tests.common.helpers.assertions: For pytest assertions
    - tests.common.macsec.macsec_platform_helper: For portchannel operations
    - tests.common.macsec.macsec_config_helper: For MACsec port enable/disable

Notes:
    - Disables loganalyzer for this test
    - ISIS_HOLDTIME = 30 seconds
    - Only runs on wan-pub-isis topology, skips all others
    - Queries IS-IS facts from duthost to get neighbor state
    - Checks IS-IS neighbor state is "Up" in neighbors['1'] dictionary
    - Waits up to 30 seconds for portchannel to come Up (5s interval, 5s delay)
    - Waits up to 30 seconds for IS-IS neighbor to reach Up state (6s interval,
      5s delay)
    - Waits up to 30 seconds for MACsec interface state changes (3s interval)
    - Only checks IS-IS neighbor state when portchannel is Up
    - Test iterates through all controlled links for comprehensive validation
    - Supports portchannel interfaces that may flap during MACsec state changes
=============================================================================
"""
import pytest
import logging

from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from tests.common.macsec.macsec_platform_helper import get_portchannel
from tests.common.macsec.macsec_platform_helper import find_portchannel_from_member
from tests.common.macsec.macsec_config_helper import enable_macsec_port, disable_macsec_port


logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.macsec_required,
    pytest.mark.topology("wan-pub-isis"),
]

ISIS_HOLDTIME = 30


def check_isis_established(duthost, nbr_name):
    isis_facts = duthost.isis_facts()["ansible_facts"]['isis_facts']

    if nbr_name not in isis_facts['neighbors']['1'].keys():
        return False
    logger.info("isis state {}".format(isis_facts['neighbors']['1'][nbr_name]['state']))
    return isis_facts['neighbors']['1'][nbr_name]['state'] == "Up"


def get_portchannel_state(duthost, ctrl_port):
    # Wait PortChannel up, which might flap if having one port member
    return wait_until(ISIS_HOLDTIME, 5, 5, lambda: find_portchannel_from_member(
                    ctrl_port, get_portchannel(duthost))["status"] == "Up")


def verify_isis_established_result(duthost, ctrl_port, nbr):
    # Check IS-IS neighbor when PortChannel is UP
    if get_portchannel_state(duthost, ctrl_port):
        pytest_assert(wait_until(ISIS_HOLDTIME, 6, 5, check_isis_established, duthost, nbr['name']),
                      "IS-IS neighbor is not UP.")


@pytest.mark.disable_loganalyzer
def test_isis_over_macsec(tbinfo, duthost, ctrl_links, upstream_links, profile_name, wait_mka_establish):
    if tbinfo['topo']['name'] != 'wan-pub-isis':
        pytest.skip("Skip as isis over macsec test only support on wan-pub-isis vtestbed")

    # Ensure the IS-IS sessions have been established
    for ctrl_port, nbr in ctrl_links.items():
        verify_isis_established_result(duthost, ctrl_port, nbr)

    # Check the IS-IS sessions are present after port macsec disabled
    for ctrl_port, nbr in ctrl_links.items():
        disable_macsec_port(duthost, ctrl_port)
        disable_macsec_port(nbr["host"], nbr["port"])
        wait_until(ISIS_HOLDTIME, 3, 0,
                   lambda: not duthost.iface_macsec_ok(ctrl_port) and
                   not nbr["host"].iface_macsec_ok(nbr["port"]))
        verify_isis_established_result(duthost, ctrl_port, nbr)

    # Check the IS-IS sessions are present after port macsec enabled
    for ctrl_port, nbr in ctrl_links.items():
        enable_macsec_port(duthost, ctrl_port, profile_name)
        enable_macsec_port(nbr["host"], nbr["port"], profile_name)
        wait_until(ISIS_HOLDTIME, 3, 0,
                   lambda: duthost.iface_macsec_ok(ctrl_port) and
                   nbr["host"].iface_macsec_ok(nbr["port"]))
        verify_isis_established_result(duthost, ctrl_port, nbr)
