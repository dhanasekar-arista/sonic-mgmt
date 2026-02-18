"""
=============================================================================
Module: dhcp_server
File: test_dhcp_server_stress.py
=============================================================================

Description:
    Stress test suite for SONiC DHCP server to validate behavior under concurrent client
    requests. This module tests the server's ability to handle multiple simultaneous DHCP
    client requests from all VLAN member ports, ensuring proper lease assignment and
    server responsiveness under load.

Test Intent:
    - test_dhcp_server_with_multiple_dhcp_clients: Verify all ports receive IP assignments when requesting simultaneously (stress test with concurrent dhclient requests)

Topology:
    - mx: Management extended topology with DHCP relay and server containers

Fixtures Used:
    - dhcp_client_setup_teardown_on_ptf: Module-level fixture to install/remove isc-dhcp-client on PTF host
    - parse_vlan_setting_from_running_config: Module-level fixture to parse VLAN configuration (gateway, netmask, hosts, members)
    - enable_sonic_dhcpv4_relay_agent: Enables SONiC DHCPv4 relay agent (isc-relay-agent or sonic-relay-agent)
    - dhcp_server_setup_teardown: Module-level setup to enable dhcp_server feature (inherited from conftest)
    - clean_dhcp_server_config_after_test: Function-level cleanup (inherited from conftest)

Dependencies:
    - PTF host with isc-dhcp-client package installed (dhclient command)
    - dhcp_server_test_common: Helper functions for DHCP configuration
    - CONFIG_DB tables: DHCP_SERVER_IPV4, DHCP_SERVER_IPV4_RANGE, DHCP_SERVER_IPV4_PORT
    - dhcp_server container with kea-dhcp4 process
    - dhcp_relay container with dhcprelayd process
    - HTTP proxy credentials for apt-get on PTF host (if required)

Notes:
    - Tests are parameterized with relay_agent (isc-relay-agent or sonic-relay-agent)
    - Stress test launches dhclient on all VLAN member interfaces simultaneously using -nw (no wait) flag
    - Test waits up to 20 seconds for all expected IPs to appear on PTF interfaces
    - Each VLAN member port is assigned a single IP from the configured range
    - Test uses real dhclient from isc-dhcp-client package (not PTF packet generator)
    - Cleanup releases all DHCP leases using dhclient -r and kills any remaining dhclient processes
    - Test validates server can handle concurrent Discover/Request from multiple clients
    - Requires at least 2 VLAN members and 2 available IPs for testing
    - Gateway IP is excluded from assignment pool to avoid conflicts

=============================================================================
"""

import logging
import ipaddress
import pytest
from tests.common.utilities import wait_until
from tests.common.helpers.assertions import pytest_assert
from dhcp_server_test_common import apply_dhcp_server_config_gcu, empty_config_patch, \
        append_common_config_patch
from tests.common.dhcp_relay_utils import enable_sonic_dhcpv4_relay_agent    # noqa: F401

pytestmark = [
    pytest.mark.topology('mx'),
    pytest.mark.parametrize("relay_agent", ["isc-relay-agent", "sonic-relay-agent"]),
]


@pytest.fixture(scope="module", autouse=True)
def dhcp_client_setup_teardown_on_ptf(ptfhost, creds):
    http_proxy = creds.get("proxy_env", {}).get("http_proxy", "")
    http_param = "-o Acquire::http::proxy='{}'".format(http_proxy) if http_proxy != "" else ""
    ptfhost.shell("apt-get {} update".format(http_param), module_ignore_errors=True)
    ptfhost.shell("apt-get {} install isc-dhcp-client -y".format(http_param))

    yield

    ptfhost.shell("apt-get remove isc-dhcp-client -y", module_ignore_errors=True)


@pytest.fixture(scope="module")
def parse_vlan_setting_from_running_config(duthost, tbinfo):
    vlan_brief = duthost.get_vlan_brief()
    first_vlan_name = list(vlan_brief.keys())[0]
    first_vlan_info = list(vlan_brief.values())[0]
    first_vlan_prefix = first_vlan_info['interface_ipv4'][0]
    disabled_host_interfaces = tbinfo['topo']['properties']['topology'].get('disabled_host_interfaces', [])
    connected_ptf_ports_idx = [interface for interface in
                               tbinfo['topo']['properties']['topology'].get('host_interfaces', [])
                               if interface not in disabled_host_interfaces]
    dut_intf_to_ptf_index = duthost.get_extended_minigraph_facts(tbinfo)['minigraph_ptf_indices']
    connected_dut_intf_to_ptf_index = {k: v for k, v in dut_intf_to_ptf_index.items() if v in connected_ptf_ports_idx}
    vlan_members = first_vlan_info['members']
    vlan_member_with_ptf_idx = [(member, connected_dut_intf_to_ptf_index[member])
                                for member in vlan_members if member in connected_dut_intf_to_ptf_index]
    pytest_assert(len(vlan_member_with_ptf_idx) >= 2, 'Vlan members is too little for testing')
    vlan_net = ipaddress.ip_network(address=first_vlan_prefix, strict=False)
    vlan_gateway = first_vlan_prefix.split('/')[0]
    vlan_hosts = [str(host) for host in vlan_net.hosts()]
    # to avoid configurate an range contains gateway ip, simply ignore all ip before gateway and gateway itself
    vlan_hosts_after_gateway = vlan_hosts[vlan_hosts.index(vlan_gateway) + 1:]
    pytest_assert(len(vlan_hosts_after_gateway) >= 2, 'Vlan size is too small for testing')
    vlan_setting = {
        'vlan_name': first_vlan_name,
        'vlan_gateway': vlan_gateway,
        'vlan_subnet_mask': str(vlan_net.netmask),
        'vlan_hosts': vlan_hosts_after_gateway,
        'vlan_member_with_ptf_idx': vlan_member_with_ptf_idx,
    }

    logging.info("The vlan_setting before test is %s" % vlan_setting)
    return vlan_setting['vlan_name'], \
        vlan_setting['vlan_gateway'], \
        vlan_setting['vlan_subnet_mask'], \
        vlan_setting['vlan_hosts'], \
        vlan_setting['vlan_member_with_ptf_idx']


def test_dhcp_server_with_multiple_dhcp_clients(
    duthost,
    ptfhost,
    parse_vlan_setting_from_running_config,
    enable_sonic_dhcpv4_relay_agent,  # noqa: F811
    relay_agent
):
    """
        Make sure all ports can get assigend ip when all ports request ip at same time
    """
    vlan_name, gateway, net_mask, vlan_hosts, vlan_members_with_ptf_idx = parse_vlan_setting_from_running_config
    start_command = " && ".join(["dhclient -nw eth%s" % ptf_index for _, ptf_index in vlan_members_with_ptf_idx])
    end_command = " ; ".join(["dhclient -r eth%s" % ptf_index for _, ptf_index in vlan_members_with_ptf_idx])
    try:
        config_to_apply = empty_config_patch()
        dut_ports, _ = zip(*vlan_members_with_ptf_idx)
        exp_assigned_ip_ranges = [[ip] for ip in vlan_hosts[:len(vlan_members_with_ptf_idx)]]
        append_common_config_patch(
            config_to_apply,
            vlan_name,
            gateway,
            net_mask,
            dut_ports,
            exp_assigned_ip_ranges
        )
        apply_dhcp_server_config_gcu(duthost, config_to_apply)
        ptfhost.shell(start_command)

        def all_ip_shown_up(ptfhost, expected_assigned_ips):
            ip_addr_output = ptfhost.shell("ip addr")['stdout']
            for expected_ip in expected_assigned_ips:
                if expected_ip not in ip_addr_output:
                    return False
            return True
        expected_assigned_ips = [range[0] for range in exp_assigned_ip_ranges]
        pytest_assert(
            wait_until(20, 1, 1,
                       all_ip_shown_up,
                       ptfhost,
                       expected_assigned_ips),
            'Not all configurated IP shown up on ptf interfaces'
        )
    finally:
        ptfhost.shell(end_command, module_ignore_errors=True)
        ptfhost.shell("killall dhclient", module_ignore_errors=True)
