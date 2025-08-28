"""
BGP Debug Information Collector

This module provides comprehensive debug information collection for BGP neighbor failures,
specifically designed to help root cause issues like the 10.0.1.59 Active state failure
in dual ToR environments.

Usage:
    from tests.common.helpers.bgp_debug_collector import collect_comprehensive_bgp_debug
    debug_report = collect_comprehensive_bgp_debug(duthost, failed_neighbor_ip)
"""

import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


def collect_comprehensive_bgp_debug(duthost, neighbor_ip=None, namespace=None, save_to_file=True):
    """
    Collect comprehensive BGP debug information for root cause analysis
    
    Args:
        duthost: DUT host object
        neighbor_ip: Specific neighbor IP to debug (optional)
        namespace: BGP namespace for multi-asic (optional)
        save_to_file: Whether to save debug info to file (default: True)
        
    Returns:
        dict: Comprehensive debug information
    """
    sonic_db_cmd = "sonic-db-cli {}".format("-n " + namespace if namespace else "")
    timestamp = datetime.now().isoformat()
    
    debug_report = {
        "timestamp": timestamp,
        "duthost": duthost.hostname,
        "namespace": namespace,
        "target_neighbor": neighbor_ip,
        "system_info": {},
        "bgp_state": {},
        "network_connectivity": {},
        "mux_information": {},
        "database_state": {},
        "logs_and_events": {},
        "interface_details": {},
        "timing_analysis": {}
    }
    
    try:
        # System information
        debug_report["system_info"]["uptime"] = duthost.shell("uptime", module_ignore_errors=True)["stdout"]
        debug_report["system_info"]["load"] = duthost.shell("cat /proc/loadavg", module_ignore_errors=True)["stdout"]
        debug_report["system_info"]["memory"] = duthost.shell("free -h", module_ignore_errors=True)["stdout"]
        debug_report["system_info"]["docker_stats"] = duthost.shell("docker stats --no-stream", module_ignore_errors=True)["stdout"]
        
        # BGP comprehensive state
        debug_report["bgp_state"]["summary"] = duthost.shell("show ip bgp summary", module_ignore_errors=True)["stdout"]
        debug_report["bgp_state"]["neighbors"] = duthost.shell("show ip bgp neighbors", module_ignore_errors=True)["stdout"]
        debug_report["bgp_state"]["routes"] = duthost.shell("show ip bgp", module_ignore_errors=True)["stdout"]
        debug_report["bgp_state"]["ipv6_summary"] = duthost.shell("show ipv6 bgp summary", module_ignore_errors=True)["stdout"]
        
        if neighbor_ip:
            debug_report["bgp_state"]["specific_neighbor"] = duthost.shell(f"show ip bgp neighbor {neighbor_ip}", module_ignore_errors=True)["stdout"]
            debug_report["bgp_state"]["neighbor_routes"] = duthost.shell(f"show ip bgp neighbor {neighbor_ip} routes", module_ignore_errors=True)["stdout"]
            debug_report["bgp_state"]["neighbor_advertised"] = duthost.shell(f"show ip bgp neighbor {neighbor_ip} advertised-routes", module_ignore_errors=True)["stdout"]
        
        # Network connectivity analysis
        if neighbor_ip:
            debug_report["network_connectivity"]["ping"] = duthost.shell(f"ping -c 5 {neighbor_ip}", module_ignore_errors=True)["stdout"]
            debug_report["network_connectivity"]["traceroute"] = duthost.shell(f"traceroute {neighbor_ip}", module_ignore_errors=True)["stdout"]
            debug_report["network_connectivity"]["route"] = duthost.shell(f"ip route get {neighbor_ip}", module_ignore_errors=True)["stdout"]
        
        debug_report["network_connectivity"]["arp_table"] = duthost.shell("ip neigh show", module_ignore_errors=True)["stdout"]
        debug_report["network_connectivity"]["route_table"] = duthost.shell("ip route show", module_ignore_errors=True)["stdout"]
        
        # MUX information for dual ToR debugging
        debug_report["mux_information"]["mux_status"] = duthost.shell("show mux status", module_ignore_errors=True)["stdout"]
        debug_report["mux_information"]["mux_config"] = duthost.shell("show mux config", module_ignore_errors=True)["stdout"]
        debug_report["mux_information"]["linkmgrd_status"] = duthost.shell("docker exec mux supervisorctl status", module_ignore_errors=True)["stdout"]
        
        # Database state analysis
        debug_report["database_state"]["neigh_state_table"] = duthost.shell(f'{sonic_db_cmd} STATE_DB KEYS "NEIGH_STATE_TABLE*"', module_ignore_errors=True)["stdout"]
        debug_report["database_state"]["bgp_state_table"] = duthost.shell(f'{sonic_db_cmd} STATE_DB KEYS "BGP_STATE*"', module_ignore_errors=True)["stdout"]
        debug_report["database_state"]["bgp_neighbor_config"] = duthost.shell(f'{sonic_db_cmd} CONFIG_DB KEYS "BGP_NEIGHBOR*"', module_ignore_errors=True)["stdout"]
        
        if neighbor_ip:
            debug_report["database_state"]["neighbor_state_details"] = duthost.shell(f'{sonic_db_cmd} STATE_DB HGETALL "NEIGH_STATE_TABLE|{neighbor_ip}"', module_ignore_errors=True)["stdout"]
            debug_report["database_state"]["neighbor_config_details"] = duthost.shell(f'{sonic_db_cmd} CONFIG_DB HGETALL "BGP_NEIGHBOR|{neighbor_ip}"', module_ignore_errors=True)["stdout"]
        
        # Logs and events
        debug_report["logs_and_events"]["bgp_container_logs"] = duthost.shell("docker logs --tail 100 bgp", module_ignore_errors=True)["stdout"]
        debug_report["logs_and_events"]["bgpd_logs"] = duthost.shell("docker exec bgp tail -100 /var/log/frr/bgpd.log", module_ignore_errors=True)["stdout"]
        debug_report["logs_and_events"]["zebra_logs"] = duthost.shell("docker exec bgp tail -100 /var/log/frr/zebra.log", module_ignore_errors=True)["stdout"]
        debug_report["logs_and_events"]["systemd_bgp"] = duthost.shell("journalctl -u bgp --since '10 minutes ago' --no-pager", module_ignore_errors=True)["stdout"]
        debug_report["logs_and_events"]["recent_syslog"] = duthost.shell("tail -200 /var/log/syslog | grep -E '(bgp|mux|link|interface)'", module_ignore_errors=True)["stdout"]
        
        # Interface details
        debug_report["interface_details"]["all_interfaces"] = duthost.shell("show interface status", module_ignore_errors=True)["stdout"]
        debug_report["interface_details"]["port_channels"] = duthost.shell("show interface portchannel", module_ignore_errors=True)["stdout"]
        debug_report["interface_details"]["ip_interfaces"] = duthost.shell("show ip interface", module_ignore_errors=True)["stdout"]
        
        # Timing analysis for race conditions
        debug_report["timing_analysis"]["process_list"] = duthost.shell("ps aux | grep -E '(bgp|mux|link)'", module_ignore_errors=True)["stdout"]
        debug_report["timing_analysis"]["network_stats"] = duthost.shell("cat /proc/net/netstat", module_ignore_errors=True)["stdout"]
        debug_report["timing_analysis"]["tcp_connections"] = duthost.shell("ss -tuln | grep 179", module_ignore_errors=True)["stdout"]
        
    except Exception as e:
        debug_report["collection_error"] = f"Debug collection failed: {str(e)}"
        logger.error(f"Failed to collect comprehensive BGP debug info: {e}")
    
    # Save to file if requested
    if save_to_file:
        try:
            debug_filename = f"/tmp/bgp_debug_{duthost.hostname}_{neighbor_ip or 'all'}_{timestamp.replace(':', '-')}.json"
            duthost.copy(content=json.dumps(debug_report, indent=2), dest=debug_filename)
            debug_report["debug_file_path"] = debug_filename
            logger.info(f"BGP debug information saved to: {debug_filename}")
        except Exception as e:
            logger.error(f"Failed to save debug file: {e}")
    
    return debug_report


def analyze_bgp_failure_patterns(debug_report):
    """
    Analyze debug report for common BGP failure patterns
    
    Args:
        debug_report: Output from collect_comprehensive_bgp_debug
        
    Returns:
        dict: Analysis results with potential root causes
    """
    analysis = {
        "potential_causes": [],
        "recommendations": [],
        "severity": "unknown"
    }
    
    try:
        # Check for MUX-related issues
        mux_status = debug_report.get("mux_information", {}).get("mux_status", "")
        if "standby" in mux_status.lower() or "suspend" in debug_report.get("logs_and_events", {}).get("recent_syslog", ""):
            analysis["potential_causes"].append("MUX state transition interference")
            analysis["recommendations"].append("Check MUX switchover timing and BGP hold timers")
        
        # Check for interface issues
        interface_logs = debug_report.get("logs_and_events", {}).get("recent_syslog", "")
        if "link down" in interface_logs.lower() or "interface" in interface_logs.lower():
            analysis["potential_causes"].append("Interface connectivity issues")
            analysis["recommendations"].append("Verify physical layer and interface configuration")
        
        # Check for timing/race conditions
        if "active" in debug_report.get("bgp_state", {}).get("summary", "").lower():
            analysis["potential_causes"].append("BGP session establishment timeout")
            analysis["recommendations"].append("Increase BGP hold timers or check network latency")
        
        # Check for configuration mismatches
        config_neighbors = debug_report.get("database_state", {}).get("bgp_neighbor_config", "")
        if neighbor_ip and neighbor_ip not in config_neighbors:
            analysis["potential_causes"].append("Missing BGP neighbor configuration")
            analysis["recommendations"].append("Verify BGP neighbor is properly configured")
        
        analysis["severity"] = "high" if len(analysis["potential_causes"]) > 2 else "medium"
        
    except Exception as e:
        analysis["analysis_error"] = f"Pattern analysis failed: {str(e)}"
    
    return analysis
