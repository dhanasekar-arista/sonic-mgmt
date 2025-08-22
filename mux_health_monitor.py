"""
Quick Fix for Mux Health Monitoring in Container Checker Tests

Add this to test_container_checker.py to detect and handle linkmgrd restart issues.
"""

import json
import time
import logging

def add_mux_health_monitoring():
    """
    This function contains the code snippets to add to test_container_checker.py
    """
    
    # 1. ADD THIS FUNCTION after line 350 in test_container_checker.py
    def check_and_log_mux_state(duthost, context="", expect_healthy=False):
        """
        Check and log mux state with detailed debugging.
        """
        logger.info(f"=== MUX STATE CHECK - {context.upper()} ===")
        
        try:
            # Check if mux cables exist
            result = duthost.shell("show muxcable status --json", module_ignore_errors=True)
            if result.get('rc') != 0:
                logger.info("No mux cables found on this device")
                return True
                
            mux_data = json.loads(result.get('stdout', '{}'))
            
            # Check linkmgrd status
            linkmgrd_result = duthost.shell("docker exec mux supervisorctl status linkmgrd", module_ignore_errors=True)
            linkmgrd_status = linkmgrd_result.get('stdout', '')
            
            # Extract linkmgrd uptime
            linkmgrd_uptime = "unknown"
            linkmgrd_pid = "unknown"
            for line in linkmgrd_status.split('\n'):
                if 'linkmgrd' in line and 'RUNNING' in line:
                    parts = line.split()
                    if len(parts) >= 6:
                        linkmgrd_pid = parts[3].rstrip(',')
                        linkmgrd_uptime = ' '.join(parts[5:])
                        break
            
            logger.info(f"Linkmgrd: PID={linkmgrd_pid}, uptime={linkmgrd_uptime}")
            
            # Analyze mux ports
            uninitialized_ports = []
            inconsistent_ports = []
            total_ports = 0
            
            for port, status in mux_data.get('MUX_CABLE', {}).items():
                total_ports += 1
                health = status.get('HEALTH', '')
                hwstatus = status.get('HWSTATUS', '')
                
                if health == 'uninitialized':
                    uninitialized_ports.append(port)
                if hwstatus == 'inconsistent':
                    inconsistent_ports.append(port)
                    
                logger.debug(f"Port {port}: STATUS={status.get('STATUS')}, HEALTH={health}, HWSTATUS={hwstatus}")
            
            # Log summary
            logger.info(f"Total mux ports: {total_ports}")
            if uninitialized_ports:
                logger.warning(f"🚨 UNINITIALIZED health ports ({len(uninitialized_ports)}): {uninitialized_ports}")
            if inconsistent_ports:
                logger.warning(f"🚨 INCONSISTENT hwstatus ports ({len(inconsistent_ports)}): {inconsistent_ports}")
                
            if not uninitialized_ports and not inconsistent_ports:
                logger.info("✅ All mux ports healthy and consistent")
                return True
            else:
                logger.warning(f"❌ Mux issues detected: {len(uninitialized_ports)} uninitialized, {len(inconsistent_ports)} inconsistent")
                return False
                
        except Exception as e:
            logger.error(f"Failed to check mux state: {e}")
            return False

    # 2. REPLACE lines 267-268 in test_container_checker_telemetry function with:
    def enhanced_config_reload_section():
        """
        Enhanced config reload section to replace lines 267-268
        """
        # Check pre-reload mux state
        logger.info("🔍 Pre-reload mux state check...")
        pre_linkmgrd = duthost.shell("docker exec mux supervisorctl status linkmgrd | grep linkmgrd", module_ignore_errors=True).get('stdout', '')
        pre_mux_healthy = check_and_log_mux_state(duthost, "PRE-RELOAD")
        
        # Extract pre-reload PID
        pre_pid = "unknown"
        if 'RUNNING' in pre_linkmgrd and 'pid' in pre_linkmgrd:
            parts = pre_linkmgrd.split()
            if len(parts) >= 4:
                pre_pid = parts[3].rstrip(',')
        
        logger.info(f"Pre-reload linkmgrd PID: {pre_pid}")
        
        # Perform config reload
        logger.info("🔄 Performing config reload...")
        reload_start = time.time()
        config_reload(duthost, safe_reload=True)
        reload_time = time.time() - reload_start
        logger.info(f"Config reload completed in {reload_time:.2f} seconds")
        
        # Check post-reload state
        logger.info("🔍 Post-reload mux state check...")
        post_linkmgrd = duthost.shell("docker exec mux supervisorctl status linkmgrd | grep linkmgrd", module_ignore_errors=True).get('stdout', '')
        
        # Extract post-reload PID and uptime
        post_pid = "unknown"
        uptime = "unknown"
        if 'RUNNING' in post_linkmgrd:
            parts = post_linkmgrd.split()
            if len(parts) >= 6:
                post_pid = parts[3].rstrip(',')
                uptime = ' '.join(parts[5:])
        
        # Check if linkmgrd restarted
        linkmgrd_restarted = (pre_pid != "unknown" and post_pid != "unknown" and pre_pid != post_pid)
        
        if linkmgrd_restarted:
            logger.warning(f"🚨 LINKMGRD RESTART DETECTED!")
            logger.warning(f"   Pre-reload PID: {pre_pid}")
            logger.warning(f"   Post-reload PID: {post_pid}")
            logger.warning(f"   Uptime: {uptime}")
            logger.warning(f"   This may cause mux health issues requiring recovery time...")
            
            # Wait longer for mux recovery
            logger.info("⏳ Waiting for mux state recovery after linkmgrd restart...")
            
            def _wait_mux_recovery():
                healthy, _ = _check_mux_health_status(duthost)
                return healthy
                
            recovery_success = wait_until(180, 15, 0, _wait_mux_recovery)
            
            if not recovery_success:
                logger.error("🚨 MUX RECOVERY FAILED - capturing debug info...")
                check_and_log_mux_state(duthost, "RECOVERY-FAILED", log_details=True)
                
                # Check for new core dumps
                try:
                    cores = duthost.shell("ls /var/core/ | grep linkmgrd | tail -2").get('stdout', '')
                    if cores:
                        logger.error(f"Recent linkmgrd core dumps: {cores}")
                except:
                    pass
                    
                pytest_assert(False, f"Mux recovery failed after linkmgrd restart in iteration {iteration_num}")
            else:
                logger.info(f"✅ Mux recovery successful after {time.time() - reload_start:.1f}s")
        else:
            logger.info(f"✅ Linkmgrd stable: PID {post_pid}, uptime {uptime}")
            
        # Final validation
        post_mux_healthy = check_and_log_mux_state(duthost, "POST-RELOAD")
        
        if not post_mux_healthy:
            logger.warning("⚠️  Mux health issues persist after config reload")

    return enhanced_config_reload_section

# 3. USAGE INSTRUCTIONS:
"""
To apply this fix to test_container_checker.py:

1. Add the check_and_log_mux_state function after line 350
2. Replace lines 267-268 with the enhanced_config_reload_section code
3. Add import json at the top of the file

This will:
- Detect linkmgrd restarts during config reload
- Monitor mux health state transitions  
- Wait for recovery when issues are detected
- Log detailed debug information for analysis
- Fail with clear error messages when recovery fails
"""

# 4. SPECIFIC LOG ENTRIES TO LOOK FOR:
"""
When this fix is applied, look for these log entries to identify the issue:

SUCCESS CASE:
  "✅ Linkmgrd stable: PID 22, uptime 2:15:30"
  "✅ All 24 mux ports healthy and consistent"

FAILURE CASE:
  "🚨 LINKMGRD RESTART DETECTED!"
  "🚨 UNINITIALIZED health ports (24): ['Ethernet4', 'Ethernet8', ...]"  
  "🚨 INCONSISTENT hwstatus ports (24): ['Ethernet4', 'Ethernet8', ...]"
  "🚨 MUX RECOVERY FAILED - capturing debug info..."

RECOVERY CASE:
  "🚨 LINKMGRD RESTART DETECTED!"
  "⏳ Waiting for mux state recovery after linkmgrd restart..."
  "✅ Mux recovery successful after 45.2s"
"""
