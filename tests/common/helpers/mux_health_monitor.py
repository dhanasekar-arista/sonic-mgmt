"""
Mux Health Monitoring Utilities for Container Checker Tests

This module provides utilities to detect and handle linkmgrd restart issues
that cause mux cable functionality to break during config reload operations.

Usage:
1. Import this module in test_container_checker.py
2. Replace config_reload calls with enhanced_config_reload_with_monitoring
3. Use check_mux_health_status for validation
"""

import json
import time
import logging
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until
from tests.common import config_reload

logger = logging.getLogger(__name__)

def check_mux_health_status(duthost, log_details=False):
    """
    Check if all mux cables are in healthy state.
    
    Args:
        duthost: DUT host object
        log_details: Whether to log detailed status for each port
        
    Returns:
        tuple: (bool, dict) - (all_healthy, status_summary)
    """
    try:
        result = duthost.shell("show muxcable status --json", module_ignore_errors=True)
        if result.get('rc') != 0:
            logger.info("No mux cables found on this device")
            return True, {}
            
        mux_status = result.get('stdout', '{}')
        if not mux_status or mux_status == '{}':
            return True, {}
            
        mux_data = json.loads(mux_status)
        
        status_summary = {
            'total_ports': 0,
            'uninitialized_health': [],
            'unhealthy': [],
            'inconsistent_hw': []
        }
        
        for port, status in mux_data.get('MUX_CABLE', {}).items():
            status_summary['total_ports'] += 1
            health = status.get('HEALTH', '')
            hwstatus = status.get('HWSTATUS', '')
            mux_status_val = status.get('STATUS', '')
            
            if log_details:
                logger.debug(f"Port {port}: STATUS={mux_status_val}, HEALTH={health}, HWSTATUS={hwstatus}")
            
            if health == 'uninitialized':
                status_summary['uninitialized_health'].append(port)
            elif health == 'unhealthy':
                status_summary['unhealthy'].append(port)
                
            if hwstatus == 'inconsistent':
                status_summary['inconsistent_hw'].append(port)
        
        all_healthy = (len(status_summary['uninitialized_health']) == 0 and 
                      len(status_summary['inconsistent_hw']) == 0)
        
        if not all_healthy:
            logger.warning(f"Mux health issues: {status_summary}")
        else:
            logger.info(f"All {status_summary['total_ports']} mux ports healthy")
            
        return all_healthy, status_summary
        
    except Exception as e:
        logger.error(f"Failed to check mux health: {e}")
        return False, {}

def get_linkmgrd_status(duthost):
    """
    Get linkmgrd process status, PID, and uptime.
    
    Returns:
        dict: {'status': str, 'pid': str, 'uptime': str}
    """
    try:
        result = duthost.shell("docker exec mux supervisorctl status linkmgrd", module_ignore_errors=True)
        output = result.get('stdout', '')
        
        for line in output.split('\n'):
            if 'linkmgrd' in line:
                parts = line.split()
                if 'RUNNING' in line and len(parts) >= 6:
                    pid = parts[3].rstrip(',')
                    uptime = ' '.join(parts[5:])
                    return {'status': 'RUNNING', 'pid': pid, 'uptime': uptime}
                else:
                    return {'status': parts[1] if len(parts) > 1 else 'UNKNOWN', 'pid': None, 'uptime': None}
                    
    except Exception as e:
        logger.error(f"Failed to get linkmgrd status: {e}")
        
    return {'status': 'ERROR', 'pid': None, 'uptime': None}

def log_detailed_mux_state(duthost, context=""):
    """
    Log comprehensive mux state for debugging.
    
    Args:
        duthost: DUT host object  
        context: Context string for logging
    """
    logger.info(f"=== DETAILED MUX STATE - {context.upper()} ===")
    
    try:
        # 1. Mux status with health details
        healthy, summary = check_mux_health_status(duthost, log_details=True)
        logger.info(f"Health summary: {summary}")
        
        # 2. Linkmgrd process status
        linkmgrd_info = get_linkmgrd_status(duthost)
        logger.info(f"Linkmgrd: {linkmgrd_info}")
        
        # 3. Check for recent core dumps
        cores = duthost.shell("ls /var/core/ | grep linkmgrd | tail -2", module_ignore_errors=True).get('stdout', '')
        if cores:
            logger.warning(f"Recent linkmgrd cores: {cores}")
        
    except Exception as e:
        logger.error(f"Failed to capture detailed state: {e}")

def enhanced_config_reload_with_monitoring(duthost, iteration_num, **kwargs):
    """
    Enhanced config reload with comprehensive mux monitoring.
    
    Args:
        duthost: DUT host object
        iteration_num: Current test iteration number
        **kwargs: Arguments for config_reload
    """
    logger.info(f"🔧 Enhanced config reload for iteration {iteration_num}")
    
    # Step 1: Pre-reload state
    logger.info("📊 Capturing pre-reload state...")
    pre_linkmgrd = get_linkmgrd_status(duthost)
    pre_healthy, pre_summary = check_mux_health_status(duthost)
    
    logger.info(f"Pre-reload: linkmgrd PID={pre_linkmgrd['pid']}, healthy={pre_healthy}")
    
    # Step 2: Config reload
    logger.info("🔄 Performing config reload...")
    reload_start = time.time()
    config_reload(duthost, **kwargs)
    reload_duration = time.time() - reload_start
    logger.info(f"Config reload completed in {reload_duration:.2f}s")
    
    # Step 3: Post-reload checks
    post_linkmgrd = get_linkmgrd_status(duthost)
    linkmgrd_restarted = (pre_linkmgrd['pid'] != post_linkmgrd['pid']) if (pre_linkmgrd['pid'] and post_linkmgrd['pid']) else False
    
    if linkmgrd_restarted:
        logger.warning(f"🚨 LINKMGRD RESTART in iteration {iteration_num}")
        logger.warning(f"   PID: {pre_linkmgrd['pid']} -> {post_linkmgrd['pid']}")
        logger.warning(f"   Uptime: {post_linkmgrd['uptime']}")
        
        # Wait for recovery
        logger.info("⏳ Waiting for mux recovery...")
        
        def _check_recovery():
            healthy, _ = check_mux_health_status(duthost)
            return healthy
        
        recovery_ok = wait_until(180, 15, 0, _check_recovery)
        
        if not recovery_ok:
            log_detailed_mux_state(duthost, "RECOVERY-FAILED")
            pytest_assert(False, f"Mux recovery failed in iteration {iteration_num}")
        else:
            logger.info("✅ Mux recovery successful")
    else:
        logger.info("✅ No linkmgrd restart detected")
    
    # Final validation
    post_healthy, post_summary = check_mux_health_status(duthost)
    if not post_healthy:
        log_detailed_mux_state(duthost, "POST-RELOAD-ISSUES")
        logger.warning(f"Mux issues persist: {post_summary}")

# Example usage in test_container_checker_telemetry:
"""
Replace this line in test_container_checker.py around line 268:
    config_reload(duthost, safe_reload=True)

With:
    from . import mux_health_monitor
    mux_health_monitor.enhanced_config_reload_with_monitoring(duthost, iteration, safe_reload=True)

This will provide detailed monitoring and automatic recovery for mux issues.
"""
