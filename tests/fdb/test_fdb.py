"""
=============================================================================
Module: fdb
File: test_fdb.py
=============================================================================

Description:
    This module contains comprehensive FDB (Forwarding Database) tests for
    SONiC switches. It validates MAC address learning, forwarding behavior,
    FDB aging, VLAN member port handling, and PortChannel to VLAN conversion
    scenarios across different packet types.

Test Intent:
    - test_fdb: Core FDB test that validates MAC learning and forwarding for
      different packet types (ethernet, ARP request, ARP reply) across VLAN
      members and PortChannels, ensuring proper unicast forwarding and broadcast
      behavior
    - test_po2vlan_fdb: Verifies FDB functionality when converting PortChannels
      to VLAN members, testing MAC learning and forwarding after the conversion

Topology:
    Supports t0, m0, and mx topologies

Fixtures Used:
    - change_mac_addresses: Modifies PTF interface MAC addresses for testing
    - remove_ip_addresses: Cleans up IP addresses from PTF interfaces
    - disable_fdb_aging: Disables FDB aging to prevent MAC expiration during tests
    - config_active_active_dualtor_active_standby: Configures active-active dualtor
    - validate_active_active_dualtor_setup: Validates active-active dualtor setup
    - mux_server_url: Provides mux simulator URL for dualtor testing
    - toggle_all_simulator_ports_to_rand_selected_tor_m: Controls mux state
    - active_active_ports: Provides list of active-active ports
    - utils_vlan_intfs_dict_orig: Original VLAN interface dictionary
    - utils_vlan_intfs_dict_add: Additional VLAN interface dictionary
    - apply_acl_rules: Applies ACL rules for testing
    - bind_acl_table: Binds ACL table to interfaces
    - ports_list: List of ports for testing
    - setup_acl_table: Sets up ACL table for PortChannel to VLAN conversion
    - acl_rule_cleanup: Cleans up ACL rules after testing
    - vlan_intfs_dict: VLAN interface dictionary
    - setup_po2vlan: Sets up PortChannel to VLAN conversion
    - get_dummay_mac_count: Provides dummy MAC count based on topology

Dependencies:
    - ptf.testutils: PTF utilities for packet generation and verification
    - tests.common.helpers.assertions: Assertion utilities
    - tests.common.fixtures: Various fixture utilities
    - tests.common.dualtor: Dualtor-specific utilities
    - tests.common.helpers.backend_acl: ACL helper functions
    - tests.common.helpers.portchannel_to_vlan: PortChannel to VLAN helpers
    - .utils: FDB test utilities (fdb_cleanup, send_eth, send_arp_request, etc.)

Notes:
    - Tests use dummy MAC addresses with prefix 02:11:22:33 for learning
    - Different MAC counts used for different topologies to optimize runtime
    - T0-116, T0-118, dualtor-64, and standalone topologies use reduced MAC count
    - Tests validate both tagged and untagged VLAN members
    - FDB aging is disabled during tests to ensure deterministic behavior
    - PortChannel to VLAN tests apply backend ACLs to validate forwarding
    - Tests cover Ethernet, ARP request, and ARP reply packet types
    - Cleanup operations ensure FDB table is flushed before and after tests
=============================================================================
"""

import pytest
import ptf.testutils as testutils
import ptf.packet as scapy
from ptf.mask import Mask
from collections import defaultdict
import time
import itertools
import logging
import pprint
import re
import random

from tests.common.helpers.assertions import pytest_assert
from tests.common.fixtures.ptfhost_utils import change_mac_addresses        # noqa: F401
from tests.common.fixtures.ptfhost_utils import remove_ip_addresses         # noqa: F401
from tests.common.fixtures.duthost_utils import disable_fdb_aging           # noqa: F401
from tests.common.dualtor.dual_tor_utils import config_active_active_dualtor_active_standby     # noqa: F401
from tests.common.dualtor.dual_tor_utils import validate_active_active_dualtor_setup            # noqa: F401
from tests.common.dualtor.mux_simulator_control import mux_server_url, \
                                                       toggle_all_simulator_ports_to_rand_selected_tor_m    # noqa: F401
from tests.common.dualtor.dual_tor_common import active_active_ports        # noqa: F401
from .utils import fdb_cleanup, send_eth, send_arp_request, send_arp_reply, send_recv_eth
from tests.common.fixtures.duthost_utils import utils_vlan_intfs_dict_orig          # noqa: F401
from tests.common.fixtures.duthost_utils import utils_vlan_intfs_dict_add           # noqa: F401
from tests.common.helpers.backend_acl import apply_acl_rules, bind_acl_table        # noqa: F401
from tests.common.fixtures.duthost_utils import ports_list            # noqa: F401
from tests.common.helpers.portchannel_to_vlan import setup_acl_table  # noqa: F401
from tests.common.helpers.portchannel_to_vlan import acl_rule_cleanup  # noqa: F401
from tests.common.helpers.portchannel_to_vlan import vlan_intfs_dict  # noqa: F401
from tests.common.helpers.portchannel_to_vlan import setup_po2vlan    # noqa: F401

pytestmark = [
    pytest.mark.topology('t0', 'm0', 'mx'),
    pytest.mark.usefixtures('disable_fdb_aging')
]

DEFAULT_FDB_ETHERNET_TYPE = 0x1234
DUMMY_MAC_PREFIX = "02:11:22:33"
DUMMY_MAC_COUNT = 10
DUMMY_MAC_COUNT_SLIM = 2
FDB_POPULATE_SLEEP_TIMEOUT = 2
FDB_CLEAN_UP_SLEEP_TIMEOUT = 2
FDB_WAIT_EXPECTED_PACKET_TIMEOUT = 20
PKT_TYPES = ["ethernet", "arp_request", "arp_reply", "cleanup"]

logger = logging.getLogger(__name__)
