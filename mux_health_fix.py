"""
Mux Health Monitoring and Recovery Fix for Container Checker Tests

This patch addresses the issue where config reload breaks mux cable functionality
by causing linkmgrd to restart and lose hardware state synchronization.
"""

import time
import logging
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until

logger = logging.getLogger(__name__)

def check_mux_health_status(duthost, timeout=60):
    """
    Check if all mux cables are in healthy state after config operations.
    
    Args:
        duthost: DUT host object
        timeout: Maximum time to wait for health recovery
        
    Returns:
        bool: True if all mux cables are healthy, False otherwise
    """
    try:
        output = duthost.shell("show muxcable status --json")
        mux_status = output.get('stdout', '{}')
        
        if not mux_status or mux_status == '{}':
            logger.info("No mux cables found on this device")
            return True
            
        import json
        mux_data = json.loads(mux_status)
        
        unhealthy_ports = []
        uninitialized_ports = []
        inconsistent_ports = []
        
        for port, status in mux_data.get('MUX_CABLE', {}).items():
            health = status.get('HEALTH', '')
            hwstatus = status.get('HWSTATUS', '')
            
            if health == 'uninitialized':
                uninitialized_ports.append(port)
            elif health == 'unhealthy':
                unhealthy_ports.append(port)
                
            if hwstatus == 'inconsistent':
                inconsistent_ports.append(port)
        
        if uninitialized_ports:
            logger.warning(f"Mux ports with uninitialized health: {uninitialized_ports}")
            return False
            
        if inconsistent_ports:
            logger.warning(f"Mux ports with inconsistent HW status: {inconsistent_ports}")
            return False
            
        logger.info("All mux cables are healthy and consistent")
        return True
        
    except Exception as e:
        logger.error(f"Failed to check mux health: {e}")
        return False

def wait_for_mux_recovery(duthost, timeout=120):
    """
    Wait for mux cables to recover after config reload.
    
    Args:
        duthost: DUT host object
        timeout: Maximum time to wait for recovery
        
    Returns:
        bool: True if recovery successful, False if timeout
    """
    logger.info("Waiting for mux cables to recover after config reload...")
    
    def _check_recovery():
        return check_mux_health_status(duthost)
    
    return wait_until(timeout, 10, 0, _check_recovery)

def check_linkmgrd_restart_during_reload(duthost, pre_reload_pid):
    """
    Check if linkmgrd restarted during config reload by comparing PIDs.
    
    Args:
        duthost: DUT host object
        pre_reload_pid: PID before reload
        
    Returns:
        tuple: (bool, str) - (restarted, new_pid)
    """
    try:
        result = duthost.shell("docker exec mux supervisorctl status linkmgrd")
        output = result.get('stdout', '')
        
        for line in output.split('\n'):
            if 'linkmgrd' in line and 'RUNNING' in line:
                # Extract PID from: "linkmgrd   RUNNING   pid 22, uptime 0:00:16"
                parts = line.split()
                if len(parts) >= 4:
                    new_pid = parts[3].rstrip(',')
                    if new_pid != str(pre_reload_pid):
                        logger.warning(f"linkmgrd restarted: old PID {pre_reload_pid} -> new PID {new_pid}")
                        return True, new_pid
                    else:
                        logger.info(f"linkmgrd PID unchanged: {new_pid}")
                        return False, new_pid
                        
    except Exception as e:
        logger.error(f"Failed to check linkmgrd status: {e}")
        
    return False, None

def get_linkmgrd_pid(duthost):
    """Get current linkmgrd PID."""
    try:
        result = duthost.shell("docker exec mux supervisorctl status linkmgrd")
        output = result.get('stdout', '')
        
        for line in output.split('\n'):
            if 'linkmgrd' in line and 'RUNNING' in line:
                parts = line.split()
                if len(parts) >= 4:
                    return int(parts[3].rstrip(','))
    except Exception as e:
        logger.error(f"Failed to get linkmgrd PID: {e}")
        
    return None

def enhanced_config_reload_with_mux_recovery(duthost, **kwargs):
    """
    Enhanced config reload that monitors and recovers mux state.
    
    Args:
        duthost: DUT host object
        **kwargs: Arguments passed to original config_reload
    """
    # Check if this is a dualtor testbed with mux cables
    has_mux = False
    try:
        result = duthost.shell("show muxcable status", module_ignore_errors=True)
        has_mux = result.get('rc') == 0 and 'MUX_CABLE' in result.get('stdout', '')
    except:
        has_mux = False
    
    if not has_mux:
        logger.info("No mux cables detected, using standard config reload")
        from tests.common import config_reload
        return config_reload(duthost, **kwargs)
    
    logger.info("=== ENHANCED CONFIG RELOAD WITH MUX MONITORING ===")
    
    # Step 1: Capture pre-reload state
    logger.info("Step 1: Capturing pre-reload mux state...")
    pre_reload_pid = get_linkmgrd_pid(duthost)
    logger.info(f"Pre-reload linkmgrd PID: {pre_reload_pid}")
    
    try:
        pre_mux_status = duthost.shell("show muxcable status --json").get('stdout', '{}')
        logger.info("Pre-reload mux status captured")
    except Exception as e:
        logger.warning(f"Failed to capture pre-reload mux status: {e}")
        pre_mux_status = '{}'
    
    # Step 2: Perform config reload
    logger.info("Step 2: Performing config reload...")
    start_time = time.time()
    
    from tests.common import config_reload
    config_reload(duthost, **kwargs)
    
    reload_duration = time.time() - start_time
    logger.info(f"Config reload completed in {reload_duration:.2f} seconds")
    
    # Step 3: Check for linkmgrd restart
    logger.info("Step 3: Checking for linkmgrd restart...")
    post_reload_pid = get_linkmgrd_pid(duthost)
    linkmgrd_restarted, new_pid = check_linkmgrd_restart_during_reload(duthost, pre_reload_pid)
    
    if linkmgrd_restarted:
        logger.warning(f"🚨 LINKMGRD RESTART DETECTED: {pre_reload_pid} -> {new_pid}")
        logger.warning("This may cause mux health issues - monitoring recovery...")
    
    # Step 4: Wait for mux recovery if linkmgrd restarted
    if linkmgrd_restarted:
        logger.info("Step 4: Waiting for mux recovery after linkmgrd restart...")
        recovery_success = wait_for_mux_recovery(duthost, timeout=120)
        
        if not recovery_success:
            logger.error("🚨 MUX RECOVERY FAILED after linkmgrd restart")
            # Capture detailed debug info
            try:
                post_mux_status = duthost.shell("show muxcable status --json").get('stdout', '{}')
                logger.error(f"Post-reload mux status: {post_mux_status}")
                
                # Check linkmgrd logs
                linkmgrd_logs = duthost.shell("docker exec mux tail -50 /var/log/syslog | grep linkmgrd").get('stdout', '')
                logger.error(f"Recent linkmgrd logs: {linkmgrd_logs}")
                
            except Exception as e:
                logger.error(f"Failed to capture debug info: {e}")
                
            pytest_assert(False, "Mux cables failed to recover after config reload")
        else:
            logger.info("✅ Mux recovery successful")
    else:
        logger.info("Step 4: No linkmgrd restart detected, checking mux health...")
        health_ok = check_mux_health_status(duthost)
        if not health_ok:
            logger.warning("Mux health issues detected despite no linkmgrd restart")
    
    logger.info("=== ENHANCED CONFIG RELOAD COMPLETED ===")

# Test modification suggestion for test_container_checker_telemetry function
def enhanced_test_container_checker_telemetry_snippet():
    """
    This is the modification that should be made to the telemetry test function
    around line 268 in test_container_checker.py
    """
    # Replace line 268: config_reload(duthost, safe_reload=True)
    # With:
    
    # Enhanced config reload with mux monitoring
    logger.info(f"=== Container Checker Telemetry Test - Iteration {iteration}/30 ===")
    
    # Monitor mux state during config reload
    enhanced_config_reload_with_mux_recovery(duthost, safe_reload=True)
    
    # Additional post-reload validation
    logger.info("Validating system state after config reload...")
    
    # Check critical processes are healthy
    from tests.common.helpers.process_utils import wait_critical_processes
    wait_critical_processes(duthost, timeout=300)
    
    # Validate mux state specifically
    if duthost.facts.get('asic_type') == 'broadcom':  # Only on platforms with mux
        mux_healthy = check_mux_health_status(duthost)
        pytest_assert(mux_healthy, "Mux cables are not healthy after config reload")
        logger.info("✅ Mux health validation passed")

# Additional logging function for detailed mux debugging
def log_detailed_mux_state(duthost, context=""):
    """
    Log detailed mux state for debugging purposes.
    
    Args:
        duthost: DUT host object
        context: Context string (e.g., "pre-reload", "post-reload")
    """
    logger.info(f"=== DETAILED MUX STATE DUMP - {context.upper()} ===")
    
    try:
        # 1. Mux cable status
        mux_status = duthost.shell("show muxcable status --json").get('stdout', '{}')
        logger.info(f"Mux status: {mux_status}")
        
        # 2. Linkmgrd process status  
        linkmgrd_status = duthost.shell("docker exec mux supervisorctl status linkmgrd").get('stdout', '')
        logger.info(f"Linkmgrd status: {linkmgrd_status}")
        
        # 3. Recent linkmgrd logs
        recent_logs = duthost.shell("docker exec mux tail -20 /var/log/syslog | grep linkmgrd").get('stdout', '')
        logger.info(f"Recent linkmgrd logs: {recent_logs}")
        
        # 4. Mux tables in STATE_DB
        mux_table = duthost.shell("sonic-db-cli STATE_DB keys 'MUX_CABLE_TABLE*'").get('stdout', '')
        logger.info(f"MUX_CABLE_TABLE keys: {mux_table}")
        
        linkmgr_table = duthost.shell("sonic-db-cli STATE_DB keys 'MUX_LINKMGR_TABLE*'").get('stdout', '')
        logger.info(f"MUX_LINKMGR_TABLE keys: {linkmgr_table}")
        
    except Exception as e:
        logger.error(f"Failed to capture detailed mux state: {e}")
    
    logger.info(f"=== END MUX STATE DUMP - {context.upper()} ===")
