"""
=============================================================================
Module: ospf
File: test_ospf_bfd.py
=============================================================================

Description:
    This test suite validates OSPF routing protocol integration with Bidirectional
    Forwarding Detection (BFD) in SONiC. BFD provides fast failure detection for
    OSPF adjacencies, enabling rapid convergence when links fail. The tests verify
    OSPF route establishment with BFD enabled and validate that BFD detects link
    failures quickly, triggering OSPF route removal.

Test Intent:
    - test_ospf_with_bfd: Verify OSPF establishes neighbors with BFD enabled, routes are learned, and BFD detects link failures causing route removal

Topology:
    t0, t1, t2 - Supports T0, T1, and T2 topologies including multi-asic configurations

Fixtures Used:
    - ospf_Bfd_setup: Module-level fixture providing OSPF and BFD configuration including neighbor addresses and ASIC mappings
    - start_ospfd: Module-level fixture that starts the ospfd daemon in BGP containers (all ASICs for multi-asic)
    - start_bfdd: Module-level fixture that starts the bfdd daemon in BGP containers (all ASICs for multi-asic)
    - duthosts: All DUT hosts in the testbed
    - rand_one_dut_hostname: Randomly selected DUT hostname for testing

Dependencies:
    - FRRouting (FRR) ospfd and bfdd daemons running in BGP container(s)
    - vtysh command-line interface for OSPF and BFD configuration
    - Multi-asic support for distributed systems

Notes:
    - Both ospfd and bfdd daemons must be started before configuration
    - For multi-asic systems, daemons are started in each BGP container (bgp0, bgp1, etc.)
    - OSPF is configured with area 0 and /31 point-to-point neighbor networks
    - BGP routing is disabled and replaced with OSPF
    - BFD peers are configured for each OSPF neighbor IP
    - 'ip ospf bfd' is enabled on each PortChannel interface
    - BFD provides subsecond failure detection compared to OSPF hello/dead timers
    - Link failure is simulated by shutting down interfaces
    - After link failure, BFD detects the failure and OSPF removes the affected routes
    - Test waits 15 seconds after BFD configuration to allow convergence
    - Test waits 5 seconds after link shutdown for BFD/OSPF to react
    - OSPF routes are identified by 'O>' prefix in routing table
    - Helper functions extract OSPF neighbor information and interface mappings
=============================================================================
"""
import pytest
import logging
import time

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t0', 't1', 't2')
]


@pytest.fixture(scope="module")
def start_ospfd(duthosts, rand_one_dut_hostname):
    duthost = duthosts[rand_one_dut_hostname]
    cmd = 'docker exec bgp bash -c "/usr/lib/frr/ospfd &"'

    for asic in duthost.asics:
        if duthost.is_multi_asic:
            duthost.shell(cmd.replace("bgp", f"bgp{asic.asic_index}", 1))
        else:
            duthost.shell(cmd)


@pytest.fixture(scope="module")
def start_bfdd(duthosts, rand_one_dut_hostname):
    duthost = duthosts[rand_one_dut_hostname]
    cmd = 'docker exec bgp bash -c "/usr/lib/frr/bfdd &"'

    for asic in duthost.asics:
        if duthost.is_multi_asic:
            duthost.shell(cmd.replace("bgp", f"bgp{asic.asic_index}", 1))
        else:
            duthost.shell(cmd)


def test_ospf_with_bfd(ospf_Bfd_setup, duthosts, rand_one_dut_hostname,
                       start_ospfd, start_bfdd):
    setup_info_nbr_addr = ospf_Bfd_setup
    neighbor_ip_addrs = setup_info_nbr_addr.keys()
    duthost = duthosts[rand_one_dut_hostname]

    # Configure OSPF on the DUT
    net_cmds = " ".join([f"-c 'network {str(ip_addr)}/31 area 0'" for ip_addr in neighbor_ip_addrs])

    for asic in duthost.asics:
        ospf_cfg_cmd = (
            f"vtysh "
            "-c 'configure terminal' "
            "-c 'no router bgp' "
            "-c 'router ospf' "
            f"{net_cmds} "
            "-c 'do write' "
            "-c 'end'"
        )

        ospf_cfg_cmd = asic.get_vtysh_cmd_for_namespace(ospf_cfg_cmd)

        duthost.shell_cmds(cmds=[ospf_cfg_cmd], module_ignore_errors=True)

    # Enable BFD on the DUT
    for ip_addr in neighbor_ip_addrs:
        asic = setup_info_nbr_addr[ip_addr]["asic"]

        cmd = asic.get_vtysh_cmd_for_namespace((
            f"vtysh "
            "-c 'configure terminal' "
            "-c 'bfd' "
            f"-c 'peer {ip_addr}' "
            "-c 'end'"
        ))

        duthost.command(cmd)

        # # Get interface name for the neighbor
        interface_names = get_ospf_dut_interfaces(
            asic,
        ) or []

        for neighbor_id in interface_names:
            interface_name = interface_names[neighbor_id]["interface"]

            cmd = asic.get_vtysh_cmd_for_namespace((
                f"vtysh "
                "-c 'configure terminal' "
                f"-c 'interface {interface_name}' "
                "-c 'ip ospf bfd' "
                "-c 'end'"
            ))

            duthost.command(cmd)

            time.sleep(15)

            cmd = asic.get_vtysh_cmd_for_namespace('vtysh -c "show ip route ospf"')

            ospf_routes = duthost.command(cmd)['stdout'].split("\n")
            assert any(["O>" in route for route in ospf_routes])

            if interface_name:
                faulty_neighbor_ip = simulate_link_failure(setup_info_nbr_addr[ip_addr]["asic"],
                                                           interface_name)

                if faulty_neighbor_ip:
                    ospf_routes = duthost.command(cmd)['stdout'].split("\n")
                    assert all([faulty_neighbor_ip not in route for route in ospf_routes])


def simulate_link_failure(asic, interface_name):
    # Get the neighbor IP corresponding to the interface
    neighbor_ip = get_ospf_neighbor_ip(asic, interface_name)

    if not neighbor_ip:
        return

    # Shutdown the specified interface
    asic.shutdown_interface(interface_name)

    # Sleep for 5 seconds
    time.sleep(5)

    return neighbor_ip


def get_ospf_neighbor_ip(asic, interface_name):
    cmd = asic.get_vtysh_cmd_for_namespace('vtysh -c "show ip ospf neighbor"')

    ospf_neighbor_output = asic.shell(cmd)['stdout']

    for line in ospf_neighbor_output.split('\n'):
        columns = line.split()
        if len(columns) >= 7 and columns[6] == interface_name:
            return columns[0]  # Neighbor IP
    return None


def get_ospf_dut_interfaces(asic):
    cmd = asic.get_vtysh_cmd_for_namespace('vtysh -c "show ip ospf neighbor"')

    ospf_neighbor_output = asic.shell(cmd)['stdout']

    dut_int_info = {}

    # Parse the output to find the interface name corresponding to the neighbor IP
    for line in ospf_neighbor_output.split('\n'):
        columns = line.split()
        # Check if the line has at least 7 columns and if the interface column contains 'PortChannel'
        if len(columns) >= 7 and 'PortChannel' in columns[6]:
            interface_info = columns[6].split(':')
            dut_int_info[columns[0]] = {'interface': interface_info[0], 'ip': interface_info[1]}

    # Return None if no OSPF interfaces found or if they don't match the criteria
    return dut_int_info if dut_int_info else None
