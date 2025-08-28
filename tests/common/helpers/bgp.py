import jinja2
import logging
import requests

from tests.common.utilities import wait_tcp_connection

logger = logging.getLogger(__name__)


NEIGHBOR_SAVE_DEST_TMPL = "/tmp/neighbor_%s.j2"
BGP_SAVE_DEST_TMPL = "/tmp/bgp_%s.j2"


def _write_variable_from_j2_to_configdb(duthost, template_file, **kwargs):
    save_dest_path = kwargs.pop("save_dest_path", "/tmp/temp.j2")
    keep_dest_file = kwargs.pop("keep_dest_file", True)
    namespace = kwargs.pop("namespace")
    config_template = jinja2.Template(open(template_file).read())
    duthost.copy(content=config_template.render(**kwargs), dest=save_dest_path)
    duthost.asic_instance_from_namespace(namespace).write_to_config_db(save_dest_path)
    if not keep_dest_file:
        duthost.file(path=save_dest_path, state="absent")


def collect_bgp_debug_info(duthost, neighbor_ip, namespace=None):
    """Collect comprehensive debug information for BGP neighbor failures"""
    sonic_db_cmd = "sonic-db-cli {}".format("-n " + namespace if namespace else "")
    debug_info = {
        "neighbor_ip": neighbor_ip,
        "timestamp": duthost.shell("date", module_ignore_errors=True)["stdout"],
        "bgp_summary": "",
        "neighbor_details": "",
        "interface_status": "",
        "routing_table": "",
        "mux_state": "",
        "connectivity_test": "",
        "bgp_logs": "",
        "frr_logs": "",
        "zebra_logs": "",
        "state_db_info": {},
        "config_db_info": {}
    }
    
    try:
        # BGP summary and neighbor details
        debug_info["bgp_summary"] = duthost.shell("show ip bgp summary", module_ignore_errors=True)["stdout"]
        debug_info["neighbor_details"] = duthost.shell(f"show ip bgp neighbor {neighbor_ip}", module_ignore_errors=True)["stdout"]
        
        # Interface status for potential BGP connection issues
        debug_info["interface_status"] = duthost.shell("show interface status", module_ignore_errors=True)["stdout"]
        
        # Routing table to check reachability 
        debug_info["routing_table"] = duthost.shell(f"ip route get {neighbor_ip}", module_ignore_errors=True)["stdout"]
        
        # MUX state information for dual ToR scenarios
        debug_info["mux_state"] = duthost.shell("show mux status", module_ignore_errors=True)["stdout"]
        
        # Test connectivity to neighbor
        debug_info["connectivity_test"] = duthost.shell(f"ping -c 3 {neighbor_ip}", module_ignore_errors=True)["stdout"]
        
        # BGP logs from container
        debug_info["bgp_logs"] = duthost.shell("sudo tail -n 100 /var/log/frr/bgpd.log", module_ignore_errors=True)["stdout"]
        debug_info["frr_logs"] = duthost.shell("docker exec bgp ls -l /var/log/frr && docker exec bgp tail -n 100 /var/log/frr/frr.log", module_ignore_errors=True)["stdout"]
        debug_info["zebra_logs"] = duthost.shell("sudo tail -n 100 /var/log/frr/zebra.log", module_ignore_errors=True)["stdout"]
        
        # Detailed STATE_DB information
        state_commands = [
            f'{sonic_db_cmd} STATE_DB HGETALL "NEIGH_STATE_TABLE|{neighbor_ip}"',
            f'{sonic_db_cmd} STATE_DB KEYS "*{neighbor_ip}*"'
        ]
        
        for cmd in state_commands:
            result = duthost.shell(cmd, module_ignore_errors=True)
            debug_info["state_db_info"][cmd] = result["stdout"]
            
        # CONFIG_DB information
        config_commands = [
            f'{sonic_db_cmd} CONFIG_DB HGETALL "BGP_NEIGHBOR|{neighbor_ip}"',
            f'{sonic_db_cmd} CONFIG_DB KEYS "*BGP*"'
        ]
        
        for cmd in config_commands:
            result = duthost.shell(cmd, module_ignore_errors=True)
            debug_info["config_db_info"][cmd] = result["stdout"]
            
    except Exception as e:
        debug_info["error"] = f"Debug collection failed: {str(e)}"
        
    return debug_info


def run_bgp_facts(duthost, enum_asic_index):
    """compare the bgp facts between observed states and target state"""

    bgp_facts = duthost.bgp_facts(instance_id=enum_asic_index)['ansible_facts']
    namespace = duthost.get_namespace_from_asic_id(enum_asic_index)
    config_facts = duthost.config_facts(host=duthost.hostname, source="running", namespace=namespace)['ansible_facts']
    sonic_db_cmd = "sonic-db-cli {}".format("-n " + namespace if namespace else "")
    
    failed_neighbors = []
    
    for k, v in list(bgp_facts['bgp_neighbors'].items()):

        debug_info = collect_bgp_debug_info(duthost, k, namespace)
        logger.info(f"BGP DEBUG INFO for neighbor {k}:")
        logger.info(f"Timestamp: {debug_info['timestamp']}")
        logger.info(f"BGP Summary:\n{debug_info['bgp_summary']}")
        logger.info(f"Neighbor Details:\n{debug_info['neighbor_details']}")
        logger.info(f"Interface Status:\n{debug_info['interface_status']}")
        logger.info(f"Routing Table:\n{debug_info['routing_table']}")
        logger.info(f"MUX State:\n{debug_info['mux_state']}")
        logger.info(f"Connectivity Test:\n{debug_info['connectivity_test']}")
        logger.info(f"BGP Logs:\n{debug_info['bgp_logs']}")
        logger.info(f"FRR Logs:\n{debug_info['frr_logs']}")
        logger.info(f"ZEBRA Logs:\n{debug_info['zebra_logs']}")
        logger.info(f"STATE_DB Info: {debug_info['state_db_info']}")
        logger.info(f"CONFIG_DB Info: {debug_info['config_db_info']}")
        
        # Verify bgp sessions are established
        if v['state'] != 'established':
            failed_neighbors.append(k)

        assert v['state'] == 'established', (
            "BGP session not established for neighbor {}. Expected 'established', got '{}'."
        ).format(k, v['state'])
        
        # Verify local ASNs in bgp sessions
        assert v['local AS'] == int(config_facts['DEVICE_METADATA']['localhost']['bgp_asn'].encode().decode("utf-8")), (
            "Local AS mismatch for neighbor {}. Expected '{}', got '{}'."
        ).format(
            k,
            int(config_facts['DEVICE_METADATA']['localhost']['bgp_asn'].encode().decode("utf-8")),
            v['local AS']
        )
        
        # Check bgpmon functionality by validate STATE DB contains this neighbor as well
        state_fact = duthost.shell('{} STATE_DB HGET "NEIGH_STATE_TABLE|{}" "state"'
                                   .format(sonic_db_cmd, k), module_ignore_errors=False)['stdout_lines']
        peer_type = duthost.shell('{} STATE_DB HGET "NEIGH_STATE_TABLE|{}" "peerType"'
                                  .format(sonic_db_cmd, k),
                                  module_ignore_errors=False)['stdout_lines']
        
        # Enhanced debug for STATE_DB mismatches
        if state_fact[0] != "Established":
            debug_info = collect_bgp_debug_info(duthost, k, namespace)
            logger.error(f"STATE_DB BGP DEBUG INFO for neighbor {k}:")
            logger.error(f"Expected: Established, Got: {state_fact[0]}")
            logger.error(f"Full debug info: {debug_info}")
            
        assert state_fact[0] == "Established", (
            "BGP neighbor state in STATE_DB is not 'Established' for neighbor {}. "
            "Expected: 'Established', got: '{}'. Debug info collected above."
        ).format(
            k,
            state_fact[0] if state_fact else "No state found"
        )
        assert peer_type[0] == ("i-BGP" if v['remote AS'] == v['local AS'] else "e-BGP"), (
            "BGP peer type mismatch for neighbor {}. "
            "Expected '{}', got '{}'."
        ).format(
            k,
            "i-BGP" if v['remote AS'] == v['local AS'] else "e-BGP",
            peer_type[0] if peer_type else "No peer type found"
        )

    # In multi-asic, would have 'BGP_INTERNAL_NEIGHBORS' and possibly no 'BGP_NEIGHBOR' (ebgp) neighbors.
    nbrs_in_cfg_facts = {}
    nbrs_in_cfg_facts.update(config_facts.get('BGP_NEIGHBOR', {}))
    nbrs_in_cfg_facts.update(config_facts.get('BGP_INTERNAL_NEIGHBOR', {}))
    # In VoQ Chassis, we would have BGP_VOQ_CHASSIS_NEIGHBOR as well.
    nbrs_in_cfg_facts.update(config_facts.get('BGP_VOQ_CHASSIS_NEIGHBOR', {}))
    for k, v in list(nbrs_in_cfg_facts.items()):
        # Compare the bgp neighbors name with config db bgp neighbors name
        assert v['name'] == bgp_facts['bgp_neighbors'][k]['description'], (
            "BGP neighbor name mismatch for neighbor. "
            "Expected '{}', got '{}'."
        ).format(
            v['name'],
            bgp_facts['bgp_neighbors'][k]['description']
        )
        # Compare the bgp neighbors ASN with config db
        assert int(v['asn'].encode().decode("utf-8")) == bgp_facts['bgp_neighbors'][k]['remote AS'], (
            "BGP remote AS number mismatch for neighbor. "
            "Expected remote AS: '{}', got: '{}'."
        ).format(
            int(v['asn'].encode().decode("utf-8")),
            bgp_facts['bgp_neighbors'][k]['remote AS']
        )


class BGPNeighbor(object):

    def __init__(self, duthost, ptfhost, name,
                 neighbor_ip, neighbor_asn,
                 dut_ip, dut_asn, port, neigh_type=None,
                 namespace=None, is_multihop=False, is_passive=False, debug=False):
        self.duthost = duthost
        self.ptfhost = ptfhost
        self.ptfip = ptfhost.mgmt_ip
        self.name = name
        self.ip = neighbor_ip
        self.asn = neighbor_asn
        self.peer_ip = dut_ip
        self.peer_asn = dut_asn
        self.port = port
        self.type = neigh_type
        self.namespace = namespace
        self.is_passive = is_passive
        self.is_multihop = not is_passive and is_multihop
        self.debug = debug

    def start_session(self):
        """Start the BGP session."""
        logging.debug("start bgp session %s", self.name)

        if not self.is_passive:
            _write_variable_from_j2_to_configdb(
                self.duthost,
                "bgp/templates/neighbor_metadata_template.j2",
                namespace=self.namespace,
                save_dest_path=NEIGHBOR_SAVE_DEST_TMPL % self.name,
                neighbor_name=self.name,
                neighbor_lo_addr=self.ip,
                neighbor_mgmt_addr=self.ip,
                neighbor_hwsku=None,
                neighbor_type=self.type
            )

            _write_variable_from_j2_to_configdb(
                self.duthost,
                "bgp/templates/bgp_template.j2",
                namespace=self.namespace,
                save_dest_path=BGP_SAVE_DEST_TMPL % self.name,
                db_table_name="BGP_NEIGHBOR",
                peer_addr=self.ip,
                asn=self.asn,
                local_addr=self.peer_ip,
                peer_name=self.name
            )

        self.ptfhost.exabgp(
            name=self.name,
            state="started",
            local_ip=self.ip,
            router_id=self.ip,
            peer_ip=self.peer_ip,
            local_asn=self.asn,
            peer_asn=self.peer_asn,
            port=self.port,
            debug=self.debug
        )
        if not wait_tcp_connection(self.ptfhost, self.ptfip, self.port, timeout_s=60):
            raise RuntimeError("Failed to start BGP neighbor %s" % self.name)

        if self.is_multihop:
            allow_ebgp_multihop_cmd = (
                "vtysh "
                "-c 'configure terminal' "
                "-c 'router bgp %s' "
                "-c 'neighbor %s ebgp-multihop'"
            )
            allow_ebgp_multihop_cmd %= (self.peer_asn, self.ip)
            self.duthost.shell(allow_ebgp_multihop_cmd)

    def stop_session(self):
        """Stop the BGP session."""
        logging.debug("stop bgp session %s", self.name)
        if not self.is_passive:
            for asichost in self.duthost.asics:
                asichost.run_sonic_db_cli_cmd("CONFIG_DB del 'BGP_NEIGHBOR|{}'".format(self.ip))
                asichost.run_sonic_db_cli_cmd("CONFIG_DB del 'DEVICE_NEIGHBOR_METADATA|{}'".format(self.name))
        self.ptfhost.exabgp(name=self.name, state="absent")

    def teardown_session(self):
        # error_subcode 3: Peer De-configured. References: RFC 4271
        msg = "neighbor {} teardown 3"
        msg = msg.format(self.peer_ip)
        logging.debug("teardown session: %s", msg)
        url = "http://%s:%d" % (self.ptfip, self.port)
        resp = requests.post(url, data={"commands": msg}, proxies={"http": None, "https": None})
        logging.debug("teardown session return: %s" % resp)
        assert resp.status_code == 200, (
            "Expected HTTP 200 from exabgp API, but got {}."
        ).format(
            resp.status_code
        )

        self.ptfhost.exabgp(name=self.name, state="stopped")
        if not self.is_passive:
            for asichost in self.duthost.asics:
                if asichost.namespace == self.namespace:
                    logging.debug("update CONFIG_DB admin_status to down on {}".format(asichost.namespace))
                    asichost.run_sonic_db_cli_cmd("CONFIG_DB hset 'BGP_NEIGHBOR|{}' admin_status down".format(self.ip))

    def announce_route(self, route):
        if "aspath" in route:
            msg = "announce route {prefix} next-hop {nexthop} as-path [ {aspath} ]"
        else:
            msg = "announce route {prefix} next-hop {nexthop}"
        msg = msg.format(**route)
        logging.debug("announce route: %s", msg)
        url = "http://%s:%d" % (self.ptfip, self.port)
        resp = requests.post(url, data={"commands": msg}, proxies={"http": None, "https": None})
        logging.debug("announce return: %s", resp)
        assert resp.status_code == 200, (
            "Expected HTTP 200 from exabgp API, but got {}."
        ).format(
            resp.status_code
        )

    def withdraw_route(self, route):
        if "aspath" in route:
            msg = "withdraw route {prefix} next-hop {nexthop} as-path [ {aspath} ]"
        else:
            msg = "withdraw route {prefix} next-hop {nexthop}"
        msg = msg.format(**route)
        logging.debug("withdraw route: %s", msg)
        url = "http://%s:%d" % (self.ptfip, self.port)
        resp = requests.post(url, data={"commands": msg}, proxies={"http": None, "https": None})
        logging.debug("withdraw return: %s", resp)
        assert resp.status_code == 200, (
            "Expected HTTP 200 from exabgp API, but got {}."
        ).format(
            resp.status_code
        )

    def announce_routes_batch(self, routes):
        commands = []
        for route in routes:
            cmd = "announce route {prefix} next-hop {nexthop}".format(
                prefix=route["prefix"],
                nexthop=route["nexthop"]
            )
            if "aspath" in route:
                cmd += " as-path [ {aspath} ]".format(
                    aspath=route["aspath"]
                )

            logging.debug(f"Queueing cmd '{cmd}' for batch announcement")
            commands.append(cmd)

        full_cmd = ";".join(commands)

        url = "http://%s:%d" % (self.ptfip, self.port)
        resp = requests.post(url, data={"commands": full_cmd}, proxies={"http": None, "https": None})
        logging.debug("announce return: %s", resp)
        assert resp.status_code == 200, (
            "Expected HTTP 200 from exabgp API, but got {}."
        ).format(
            resp.status_code
        )

    def withdraw_routes_batch(self, routes):
        commands = []
        for route in routes:
            cmd = "withdraw route {prefix} next-hop {nexthop}".format(
                prefix=route["prefix"],
                nexthop=route["nexthop"]
            )
            if "aspath" in route:
                cmd += " as-path [ {aspath} ]".format(
                    aspath=route["aspath"]
                )

            logging.debug(f"Queueing cmd '{cmd}' for batch withdraw")
            commands.append(cmd)

        full_cmd = ";".join(commands)

        url = "http://%s:%d" % (self.ptfip, self.port)
        resp = requests.post(url, data={"commands": full_cmd}, proxies={"http": None, "https": None})
        logging.debug("announce return: %s", resp)
        assert resp.status_code == 200, (
            "Expected HTTP 200 from exabgp API, but got {}."
        ).format(
            resp.status_code
        )
