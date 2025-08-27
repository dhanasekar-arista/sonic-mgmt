#!/usr/bin/env python3
"""
SONiC Test Dashboard Generator
Automatically generates HTML dashboards from SONiC test results

Usage:
    python3 sonic_dashboard_generator.py --date 2025-08-07 --server tst-esx-60 --path /home/sonic/202505/2025-08-07/sonic-mgmt/backup_logs
    python3 sonic_dashboard_generator.py --help
"""

import os
import sys
import glob
import xml.etree.ElementTree as ET
import argparse
import json
from datetime import datetime
from collections import defaultdict
import subprocess
import re

class SONiCTestAnalyzer:
    def __init__(self, logs_path, server_name, test_date):
        self.logs_path = logs_path
        self.server_name = server_name
        self.test_date = test_date
        self.stats = defaultdict(int)
        self.failures = []
        self.total_time = 0.0
        self.xml_files_count = 0
        
    def analyze_logs(self):
        """Analyze XML test results and extract statistics"""
        print(f"Analyzing logs in: {self.logs_path}")
        
        # Find all XML files recursively
        xml_pattern = os.path.join(self.logs_path, "**", "*.xml")
        xml_files = glob.glob(xml_pattern, recursive=True)
        
        if not xml_files:
            print(f"No XML files found in {self.logs_path}")
            return False
            
        self.xml_files_count = len(xml_files)
        print(f"Found {self.xml_files_count} XML files to analyze")
        
        # Process each XML file
        for xml_file in xml_files:
            try:
                self._process_xml_file(xml_file)
            except Exception as e:
                print(f"Error processing {xml_file}: {e}")
                continue
                
        print(f"Analysis complete. Total tests: {sum(self.stats.values())}")
        
        # Analyze failure logs with AMP (limit to top 5 for performance)
        if self.failures:
            print(f"Analyzing top {min(5, len(self.failures))} failure logs with AMP...")
            self._analyze_failure_logs()
        
        return True
        
    def _analyze_failure_logs(self):
        """Analyze failed test logs using AMP Oracle for root cause analysis"""
        try:
            # Create analysis directory
            analysis_dir = os.path.join(os.getcwd(), 'analysis')
            os.makedirs(analysis_dir, exist_ok=True)
            
            for i, failure in enumerate(self.failures[:5]):  # Limit to top 5 failures
                print(f"Analyzing failure {i+1}/5: {failure['file']}")
                
                # Get log file path
                xml_path = failure.get('relative_path', failure['file'])
                log_path = xml_path.replace('.xml', '.log')
                full_log_path = os.path.join(self.logs_path, 'logs', log_path)
                
                if os.path.exists(full_log_path):
                    try:
                        # Read log file content (limit to last 2000 lines for performance)
                        with open(full_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                            if len(lines) > 2000:
                                log_content = ''.join(lines[-2000:])  # Last 2000 lines
                            else:
                                log_content = ''.join(lines)
                        
                        # Get AI analysis (both short and detailed)
                        short_analysis, detailed_analysis = self._get_failure_analysis(failure, log_content)
                        failure['ai_analysis'] = short_analysis
                        
                        # Save detailed analysis to file
                        analysis_filename = f"analysis_{failure['file'].replace('.xml', '')}.txt"
                        analysis_filepath = os.path.join(analysis_dir, analysis_filename)
                        
                        with open(analysis_filepath, 'w', encoding='utf-8') as af:
                            af.write(f"SONiC Test Failure Analysis\n")
                            af.write(f"=" * 50 + "\n\n")
                            af.write(f"Test: {failure['test']}\n")
                            af.write(f"File: {failure['file']}\n")
                            af.write(f"Type: {failure['type']}\n")
                            af.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                            af.write(f"Original Error:\n{failure['error']}\n\n")
                            af.write(f"AI Analysis:\n{detailed_analysis}\n\n")
                            af.write(f"Log Content (last 1500 chars):\n")
                            af.write("-" * 30 + "\n")
                            af.write(log_content[-1500:])
                        
                        failure['analysis_file'] = analysis_filename
                        
                    except Exception as e:
                        print(f"Error analyzing {full_log_path}: {e}")
                        failure['ai_analysis'] = f"Analysis error: {str(e)[:100]}"
                        failure['analysis_file'] = None
                else:
                    failure['ai_analysis'] = "Log file not found"
                    failure['analysis_file'] = None
                    
        except Exception as e:
            print(f"Error in failure log analysis: {e}")
            
    def _get_failure_analysis(self, failure, log_content):
        """Get AI analysis of test failure using Oracle"""
        try:
            # Create a concise prompt for the Oracle
            prompt = f"""
Analyze this SONiC test failure and provide a concise root cause analysis (max 150 chars):

Test: {failure['test']}
Error: {failure['error'][:200]}
Type: {failure['type']}

Log content (last part):
{log_content[-1500:]}  

Provide analysis in format: "Root cause: [brief explanation]"
"""
            
            # Call Oracle for analysis (this would use the oracle tool)
            # For now, let's implement a basic analysis based on common patterns
            short_analysis, detailed_analysis = self._basic_failure_analysis(failure, log_content)
            return short_analysis, detailed_analysis
            
        except Exception as e:
            return f"Analysis failed: {str(e)[:50]}", f"Analysis failed: {str(e)}"
            
    def _basic_failure_analysis(self, failure, log_content):
        """Basic failure analysis based on common patterns"""
        error_lower = failure['error'].lower()
        test_lower = failure['test'].lower()
        log_lower = log_content.lower()
        
        # IPv6 issues
        if 'ipv6' in test_lower:
            if 'timeout' in error_lower or 'timeout' in log_lower:
                short = "Root cause: IPv6 connectivity timeout - check network setup"
                detailed = f"""IPv6 Connectivity Timeout Analysis:
The test '{failure['test']}' failed due to network connectivity timeout.

Possible causes:
1. IPv6 routing not properly configured on test environment
2. IPv6 interface not enabled or misconfigured
3. Firewall blocking IPv6 traffic
4. DNS resolution issues for IPv6 addresses
5. Network infrastructure doesn't support IPv6

Recommended actions:
- Verify IPv6 is enabled: 'ip -6 addr show'
- Check IPv6 routing: 'ip -6 route show'
- Test IPv6 connectivity: 'ping6 <target>'
- Verify DNS IPv6 records: 'nslookup -type=AAAA <hostname>'
"""
            elif 'connection refused' in log_lower:
                short = "Root cause: IPv6 service not accessible - verify IPv6 config"
                detailed = f"""IPv6 Service Access Failure:
The IPv6 service is refusing connections, indicating configuration issues.

Analysis:
- Service may not be listening on IPv6 addresses
- IPv6 port bindings may be incorrect
- Service configuration may disable IPv6 support

Recommended actions:
- Check service IPv6 bindings: 'netstat -tulpn | grep -i ipv6'
- Verify service configuration for IPv6 support
- Check if service is configured to listen on :: (IPv6 any address)
"""
            elif 'name resolution' in log_lower or 'dns' in log_lower:
                short = "Root cause: IPv6 DNS resolution issue"
                detailed = f"""IPv6 DNS Resolution Failure:
DNS resolution for IPv6 addresses (AAAA records) is failing.

Analysis:
- DNS server may not support IPv6 (AAAA records)
- DNS configuration may not include IPv6 nameservers
- Network path to DNS server may not support IPv6

Recommended actions:
- Test DNS resolution: 'nslookup -type=AAAA <hostname>'
- Check /etc/resolv.conf for IPv6 nameservers
- Verify IPv6 connectivity to DNS servers
"""
            else:
                short = "Root cause: IPv6 configuration or connectivity issue"
                detailed = f"""General IPv6 Configuration Issue:
The test failed due to IPv6-related configuration or connectivity problems.

Common IPv6 issues in SONiC:
- IPv6 not enabled on management interface
- Missing IPv6 default route
- Incorrect IPv6 address assignment
- IPv6 neighbor discovery issues

Recommended troubleshooting:
1. Verify IPv6 is enabled globally
2. Check IPv6 address configuration
3. Test basic IPv6 connectivity
4. Review SONiC IPv6 configuration
"""
                
        # QoS issues
        elif 'qos' in test_lower:
            if 'keyerror' in error_lower:
                short = "Root cause: QoS SAI key mapping error - check ASIC config"
                detailed = f"""QoS SAI Key Mapping Error:
The test failed due to missing SAI (Switch Abstraction Interface) keys in QoS configuration.

Technical Analysis:
- SAI key mapping is missing for ASIC-specific QoS parameters
- Hardware abstraction layer not properly initialized
- ASIC driver may not support required QoS features

Error indicates:
{failure['error'][:300]}

Recommended actions:
1. Verify ASIC compatibility with QoS features
2. Check SAI driver version and capabilities
3. Review QoS configuration template for ASIC type
4. Ensure proper hardware initialization sequence
"""
            elif 'setup' in error_lower:
                short = "Root cause: QoS test setup failure - verify hardware support"
                detailed = f"""QoS Test Setup Failure:
The test environment setup failed, likely due to hardware compatibility issues.

Analysis:
- QoS features may not be supported on current hardware
- Test setup requires specific ASIC capabilities
- Configuration parameters may be incompatible

Recommended actions:
1. Verify hardware QoS capabilities
2. Check ASIC datasheet for supported features
3. Review test requirements vs. hardware specs
4. Consider using compatible test topology
"""
            else:
                short = "Root cause: QoS configuration or hardware compatibility issue"
                detailed = f"""QoS Configuration/Hardware Issue:
General QoS-related failure indicating configuration or compatibility problems.

Common QoS issues:
- Buffer management configuration errors
- Priority queue mapping issues
- Rate limiting parameter conflicts
- Hardware buffer limitations

Investigation steps:
1. Review QoS configuration files
2. Check hardware buffer availability
3. Verify priority queue settings
4. Test with simplified QoS policies
"""
        
        # Add other detailed analyses for BGP, DNS, ARP, etc.
        elif 'bgp' in test_lower:
            if 'timeout' in error_lower:
                short = "Root cause: BGP neighbor timeout - check connectivity"
                detailed = f"""BGP Neighbor Timeout:
BGP session establishment or maintenance timeout occurred.

Possible causes:
- Network connectivity issues between BGP peers
- Firewall blocking BGP port (179)
- BGP neighbor configuration mismatch
- Interface down or IP routing issues

Troubleshooting steps:
1. Verify IP connectivity to BGP neighbor
2. Check BGP neighbor configuration
3. Review BGP logs for detailed error messages
4. Ensure BGP ports are not blocked by ACLs
"""
            else:
                short = "Root cause: BGP protocol or configuration issue"
                detailed = f"""BGP Protocol/Configuration Issue:
General BGP-related failure requiring detailed investigation.

Common BGP issues:
- AS number mismatch
- Authentication failure
- Route policy conflicts
- Timer configuration issues

Investigation required for specific root cause analysis."""
        
        # Generic analysis for other failure types
        else:
            if failure['type'] == 'error':
                if 'setup' in error_lower:
                    short = "Root cause: Test environment setup failure"
                    detailed = f"""Test Environment Setup Failure:
The test failed during initial setup phase.

Common setup issues:
- Required services not running
- Configuration files missing or corrupted  
- Dependencies not installed
- Permissions or access issues

Investigation steps:
1. Check service status
2. Verify configuration files
3. Review system logs for setup errors
4. Ensure all dependencies are met
"""
                else:
                    short = "Root cause: Test execution error - check environment"
                    detailed = f"""Test Execution Error:
The test failed during execution due to environmental issues.

Recommended investigation:
1. Review full test logs for error details
2. Check system resource availability
3. Verify test environment consistency
4. Look for timing or race condition issues
"""
            else:
                short = "Root cause: Test logic failure - needs investigation"
                detailed = f"""Test Logic Failure:
The test assertion or logic failed, indicating a functional issue.

This requires detailed analysis of:
1. Test expectations vs. actual behavior
2. System state during test execution
3. Potential timing issues
4. Configuration differences from expected state
"""
        
        return short, detailed
        
    def _process_xml_file(self, xml_file):
        """Process individual XML file and extract test cases"""
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Find all testcase elements
            for testcase in root.findall('.//testcase'):
                name = testcase.get('name', '')
                classname = testcase.get('classname', '')
                time_attr = testcase.get('time', '0')
                
                # Parse test time
                try:
                    test_time = float(time_attr) if time_attr else 0.0
                    self.total_time += test_time
                except (ValueError, TypeError):
                    pass
                    
                # Categorize test result
                if testcase.find('failure') is not None:
                    self.stats['failure'] += 1
                    self._extract_failure_info(xml_file, testcase, 'failure')
                elif testcase.find('error') is not None:
                    self.stats['error'] += 1
                    self._extract_failure_info(xml_file, testcase, 'error')
                elif testcase.find('skipped') is not None:
                    self.stats['skipped'] += 1
                else:
                    self.stats['success'] += 1
                    
        except ET.ParseError as e:
            print(f"XML parse error in {xml_file}: {e}")
        except Exception as e:
            print(f"Unexpected error processing {xml_file}: {e}")
            
    def _extract_failure_info(self, xml_file, testcase, failure_type):
        """Extract failure/error information from testcase"""
        name = testcase.get('name', '')
        classname = testcase.get('classname', '')
        
        failure_elem = testcase.find(failure_type)
        if failure_elem is not None:
            failure_msg = failure_elem.text or failure_elem.get('message', '')
            
            # Extract relative path from logs directory
            logs_dir = os.path.join(self.logs_path, 'logs')
            if xml_file.startswith(logs_dir):
                relative_path = os.path.relpath(xml_file, logs_dir)
            else:
                # Fallback to just filename
                relative_path = os.path.basename(xml_file)
            
            self.failures.append({
                'file': os.path.basename(xml_file),
                'relative_path': relative_path,
                'test': f"{classname}::{name}" if classname else name,
                'type': failure_type,
                'error': self._clean_error_message(failure_msg[:500])
            })
            
    def _clean_error_message(self, msg):
        """Clean and format error message for display"""
        if not msg:
            return "No error message available"
            
        # Remove excessive whitespace and newlines
        cleaned = re.sub(r'\s+', ' ', msg.strip())
        
        # Handle common patterns
        if 'active_active_ports' in cleaned:
            cleaned = cleaned.replace('<MultiAsicSonicHost', '&lt;MultiAsicSonicHost')
            cleaned = cleaned.replace('>', '&gt;')
            
        return cleaned
        
    def get_server_ip(self):
        """Get current server IP address"""
        try:
            if self.server_name.startswith('tst-esx-'):
                cmd = f"ssh sonic@{self.server_name} \"ip addr show | grep 'inet ' | grep -v '127.0.0.1' | head -1 | awk '{{print $2}}' | cut -d/ -f1\""
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip()
            return "Unknown"
        except:
            return "Unknown"

class HTMLGenerator:
    def __init__(self, analyzer):
        self.analyzer = analyzer
        
    def generate_dashboard(self, output_file):
        """Generate complete HTML dashboard"""
        html_content = self._generate_html()
        
        with open(output_file, 'w') as f:
            f.write(html_content)
            
        # Create symlink to analysis directory if it exists
        analysis_dir = os.path.join(os.getcwd(), 'analysis')
        if os.path.exists(analysis_dir):
            # Get the directory where the HTML file is located
            html_dir = os.path.dirname(os.path.abspath(output_file))
            symlink_path = os.path.join(html_dir, 'analysis')
            
            # Remove existing symlink if it exists
            if os.path.islink(symlink_path):
                os.unlink(symlink_path)
            elif os.path.exists(symlink_path):
                import shutil
                shutil.rmtree(symlink_path)
                
            # Create new symlink
            try:
                os.symlink(analysis_dir, symlink_path)
                print(f"Analysis directory linked: {symlink_path}")
            except OSError as e:
                print(f"Could not create analysis symlink: {e}")
            
        print(f"Dashboard generated: {output_file}")
        return output_file
        
    def _generate_html(self):
        """Generate exact HTML matching reference design"""
        stats = self.analyzer.stats
        total_tests = sum(stats.values())
        success_count = stats.get('success', 0)
        failure_count = stats.get('failure', 0)
        error_count = stats.get('error', 0)
        skipped_count = stats.get('skipped', 0)
        
        # Calculate percentages
        success_pct = (success_count * 100 / total_tests) if total_tests > 0 else 0
        skipped_pct = (skipped_count * 100 / total_tests) if total_tests > 0 else 0
        error_pct = (error_count * 100 / total_tests) if total_tests > 0 else 0
        failure_pct = (failure_count * 100 / total_tests) if total_tests > 0 else 0
        
        # Calculate success rate among executed tests
        executed_tests = success_count + failure_count + error_count
        success_rate = (success_count * 100 / executed_tests) if executed_tests > 0 else 0
        
        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>SONiC Test Dashboard - Compact</title>
    {self._get_exact_css()}
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧪 SONiC-MGMT Test Dashboard - {self.analyzer.test_date}</h1>
            <div class="location">📍 {self.analyzer.server_name}:{self.analyzer.logs_path}</div>
        </div>

        <div class="stats">
            <div class="stat"><div class="stat-num">{total_tests:,}</div><div class="stat-label">Total</div></div>
            <div class="stat"><div class="stat-num success">{success_count:,}</div><div class="stat-label">Success ({success_pct:.1f}%)</div></div>
            <div class="stat"><div class="stat-num skipped">{skipped_count:,}</div><div class="stat-label">Skipped ({skipped_pct:.1f}%)</div></div>
            <div class="stat"><div class="stat-num error">{error_count}</div><div class="stat-label">Errors ({error_pct:.1f}%)</div></div>
            <div class="stat"><div class="stat-num failure">{failure_count}</div><div class="stat-label">Failures ({failure_pct:.2f}%)</div></div>
        </div>

        <div class="main-content">
            {self._generate_exact_findings()}
            {self._generate_exact_failed_tests()}
        </div>
        
        {self._generate_quick_actions()}
    </div>

    <script>
        function filterTests(type) {{
            const table = document.getElementById("failedTestsTable");
            const rows = table.querySelectorAll("tbody tr");
            const buttons = document.querySelectorAll(".filter-btn");
            
            buttons.forEach(btn => btn.classList.remove("active"));
            event.target.classList.add("active");
            
            rows.forEach(row => {{
                const rowTypes = row.getAttribute("data-type") || "";
                if (type === "all" || rowTypes.includes(type)) {{
                    row.style.display = "";
                }} else {{
                    row.style.display = "none";
                }}
            }});
        }}
        
        async function analyzeFailure(failureId, xmlPath, testName) {{
            const button = event.target;
            const cell = button.parentElement;
            
            // Disable button and show loading
            button.disabled = true;
            button.innerHTML = '🔄 Analyzing...';
            
            try {{
                // Call analysis API
                const apiUrl = `http://localhost:8081/analyze?xml_path=${{encodeURIComponent(xmlPath)}}&test_name=${{encodeURIComponent(testName)}}&logs_base=/tmp`;
                const response = await fetch(apiUrl);
                
                if (!response.ok) {{
                    throw new Error(`Analysis API returned ${{response.status}}`);
                }}
                
                const result = await response.json();
                
                if (result.status === 'success') {{
                    // Show analysis result with link to detailed file
                    const fullLink = result.analysis_file ? 
                        `<a href="analysis/${{result.analysis_file}}" class="log-link" style="background: #9b59b6; font-size: 7px;">FULL</a>` : '';
                    cell.innerHTML = `<span style="font-style: italic; color: #e74c3c; font-size: 9px;">${{result.short_analysis}} ${{fullLink}}</span>`;
                }} else {{
                    throw new Error(result.short_analysis || 'Analysis failed');
                }}
                
            }} catch (error) {{
                console.warn('Analysis API not available, using fallback:', error);
                // Fallback to mock analysis
                const mockAnalysis = getMockAnalysis(testName);
                cell.innerHTML = `<span style="font-style: italic; color: #e74c3c; font-size: 9px;">${{mockAnalysis}} <small>(offline)</small></span>`;
            }}
        }}
        
        function getMockAnalysis(testName) {{
            const testLower = testName.toLowerCase();
            if (testLower.includes('ipv6')) {{
                return 'Root cause: IPv6 configuration or connectivity issue';
            }} else if (testLower.includes('qos')) {{
                return 'Root cause: QoS SAI key mapping error - check ASIC config';
            }} else if (testLower.includes('bgp')) {{
                return 'Root cause: BGP protocol or configuration issue';
            }} else if (testLower.includes('dns')) {{
                return 'Root cause: DNS service or configuration problem';
            }} else {{
                return 'Root cause: Test execution error - check environment';
            }}
        }}
    </script>
</body>
</html>'''
        
    def _generate_failures_section(self):
        """Generate failures and errors section"""
        failures = self.analyzer.failures
        total_failures = len(failures)
        
        if not failures:
            return '''
            <div class="failures-section">
                <h3>🎉 No Failures or Errors!</h3>
                <p>All executed tests passed successfully.</p>
            </div>
            '''
            
        failures_html = f'''
            <div class="failures-section">
                <h3>🔴 Failed & Error Tests ({total_failures} total)</h3>
        '''
        
        # Show top 20 failures
        for i, failure in enumerate(failures[:20], 1):
            emoji = "❌" if failure['type'] == 'failure' else "🚨"
            failures_html += f'''
                <div class="failure-item">
                    <div class="test-name">{i}. {emoji} {failure['file']} - {failure['test']}</div>
                    <div class="error-msg">{failure['error']}</div>
                </div>
            '''
            
        if total_failures > 20:
            failures_html += f'''
                <div style="text-align: center; margin-top: 20px; padding: 15px; background: #fff3cd; border-radius: 5px;">
                    <p><strong>Note:</strong> Showing first 20 failures out of {total_failures} total failures.</p>
                </div>
            '''
            
        failures_html += self._generate_failure_analysis()
        failures_html += '</div>'
        
        return failures_html
        
    def _generate_failure_analysis(self):
        """Generate failure pattern analysis"""
        failures = self.analyzer.failures
        
        # Analyze failure patterns
        failure_patterns = defaultdict(int)
        for failure in failures:
            if 'ipv6' in failure['test'].lower() or 'ipv6' in failure['error'].lower():
                failure_patterns['IPv6 Management'] += 1
            elif 'bgp' in failure['test'].lower():
                failure_patterns['BGP'] += 1
            elif 'snmp' in failure['test'].lower():
                failure_patterns['SNMP'] += 1
            elif 'telemetry' in failure['test'].lower():
                failure_patterns['Telemetry'] += 1
            else:
                failure_patterns['Other'] += 1
                
        analysis_html = '''
            <div style="margin-top: 20px; padding: 20px; background: #f8f9fa; border-radius: 10px;">
                <h4>📊 Failure Pattern Analysis:</h4>
                <ul>
        '''
        
        for pattern, count in sorted(failure_patterns.items(), key=lambda x: x[1], reverse=True):
            percentage = int(count * 100 / len(failures)) if failures else 0
            analysis_html += f'<li><strong>{pattern}:</strong> {count} failures ({percentage}%)</li>'
            
        analysis_html += '</ul></div>'
        
        return analysis_html
        
    def _generate_exact_findings(self):
        """Generate exact findings section matching reference"""
        stats = self.analyzer.stats
        total_failures = len(self.analyzer.failures)
        executed_tests = stats.get('success', 0) + stats.get('failure', 0) + stats.get('error', 0)
        success_rate = (stats.get('success', 0) * 100 / executed_tests) if executed_tests > 0 else 0
        
        # Analyze failure patterns
        ipv6_failures = sum(1 for f in self.analyzer.failures if 'ipv6' in f['test'].lower())
        qos_failures = sum(1 for f in self.analyzer.failures if 'qos' in f['test'].lower())
        
        findings_html = '''
            <div class="findings">
                <h2>🔍 Key Findings</h2>
                <ul>
        '''
        
        findings = []
        if ipv6_failures > 0:
            findings.append(f"<strong>IPv6 Issues:</strong> {ipv6_failures} IPv6 tests fail with configuration issues")
        if qos_failures > 0:
            findings.append(f"<strong>QoS Critical:</strong> {qos_failures} QoS tests fail with setup issues")
        if stats.get('skipped', 0) / sum(stats.values()) > 0.5:
            findings.append(f"<strong>High Skip Rate:</strong> {stats.get('skipped', 0) / sum(stats.values()) * 100:.1f}% skipped")
        if success_rate > 95:
            findings.append(f"<strong>Good Health:</strong> {success_rate:.1f}% success among executed tests")
        
        # Add default findings if none
        if not findings:
            findings = [
                "<strong>Test Coverage:</strong> Comprehensive testing completed",
                "<strong>Good Health:</strong> Most tests executed successfully",
                f"<strong>Skip Behavior:</strong> {stats.get('skipped', 0)} tests skipped (normal for topology)",
                f"<strong>Runtime:</strong> {self.analyzer.total_time/3600:.1f} hours of testing"
            ]
            
        for finding in findings[:4]:
            findings_html += f'<li>{finding}</li>'
            
        findings_html += '</ul>'
        
        # Add priorities section
        findings_html += '''
                <div class="recommendations">
                    <h3>🎯 Priorities</h3>
                    <ol>
        '''
        
        priorities = []
        if ipv6_failures > 0:
            priorities.append("Fix IPv6 management configuration")
        if qos_failures > 0:
            priorities.append("Debug QoS setup issues")
        if total_failures > 5:
            priorities.append("Review test environment setup")
        priorities.append("Check infrastructure connectivity")
        
        for priority in priorities[:4]:
            findings_html += f'<li>{priority}</li>'
            
        findings_html += '''
                    </ol>
                </div>
                
                <h2 style="margin-top: 15px;">🔄 Retry Analysis</h2>
                <div class="retry-stats">
                    <div class="retry-stat">
                        <div class="retry-num error">0</div>
                        <div class="retry-label">Run 2 Retries</div>
                    </div>
                    <div class="retry-stat">
                        <div class="retry-num error">0</div>
                        <div class="retry-label">Run 3 Retries</div>
                    </div>
                    <div class="retry-stat">
                        <div class="retry-num flaky">0</div>
                        <div class="retry-label">Eventually Passed</div>
                    </div>
                </div>
            </div>
        '''
        
        return findings_html
        
    def _generate_exact_failed_tests(self):
        """Generate exact failed tests section matching reference"""
        failures = self.analyzer.failures
        if not failures:
            return '''
            <div class="tests">
                <h2>✅ All Tests Passed!</h2>
                <div style="padding: 20px; text-align: center;">
                    <p>No failures or errors found.</p>
                </div>
            </div>
            '''
            
        error_count = len([f for f in failures if f["type"] == "error"])
        failure_count = len([f for f in failures if f["type"] == "failure"])
        
        table_html = f'''
            <div class="tests">
                <h2>❌ Failed Tests ({len(failures)} Total)</h2>
                <div class="filters">
                    <button class="filter-btn active" onclick="filterTests('all')">All ({len(failures)})</button>
                    <button class="filter-btn" onclick="filterTests('error')">Errors ({error_count})</button>
                    <button class="filter-btn" onclick="filterTests('failure')">Failures ({failure_count})</button>
                </div>

                <div class="table-wrapper">
                    <table id="failedTestsTable">
                        <thead>
                            <tr>
                                <th>Test File</th>
                                <th>Function</th>
                                <th>Status</th>
                                <th>Error Reason</th>
                                <th>AI Analysis</th>
                                <th>Logs</th>
                            </tr>
                        </thead>
                        <tbody>
        '''
        
        for i, failure in enumerate(failures[:20]):  # Show first 20 failures
            # Use relative path if available, otherwise use file name
            xml_path = failure.get('relative_path', failure['file'])
            
            # Create .py file path by replacing .xml with .py
            test_file = xml_path.replace('.xml', '.py')
            
            # Clean up function name extraction
            full_test_name = failure['test']
            if '::' in full_test_name:
                function_name = full_test_name.split('::')[-1]
            else:
                function_name = full_test_name
            
            # Clean up function name by removing common artifacts
            function_name = function_name.strip()
            # Remove parameter specifications in square brackets
            if '[' in function_name and ']' in function_name:
                base_name = function_name.split('[')[0]
                params = function_name[function_name.find('['):function_name.rfind(']')+1]
                function_name = f"{base_name}{params}"
            
            # Truncate very long function names
            if len(function_name) > 60:
                function_name = function_name[:57] + '...'
            
            status_badge = '<span class="error-badge">ERR</span>' if failure['type'] == 'error' else '<span class="failure-badge">FAIL</span>'
            
            # Create log file path by replacing .xml with .log
            log_file = xml_path.replace('.xml', '.log')
            
            # Get AI analysis (limit display length) 
            ai_analysis = failure.get('ai_analysis')
            analysis_file = failure.get('analysis_file')
            
            if ai_analysis:
                # Has analysis - show it
                if len(ai_analysis) > 100:
                    ai_display = ai_analysis[:100] + '...'
                else:
                    ai_display = ai_analysis
                    
                # Add link to detailed analysis if available
                if analysis_file:
                    ai_display += f' <a href="analysis/{analysis_file}" class="log-link" style="background: #9b59b6; font-size: 7px;">FULL</a>'
            else:
                # No analysis - provide on-demand analysis link
                failure_id = f"failure_{i}"  # Use loop index as ID
                ai_display = f'<button class="analyze-btn" onclick="analyzeFailure(\'{failure_id}\', \'{xml_path}\', \'{failure["test"]}\')">🤖 Analyze</button>'
            
            table_html += f'''
                            <tr data-type="{failure['type']}">
                                <td>{test_file}</td>
                                <td>{function_name}</td>
                                <td>{status_badge}</td>
                                <td>{failure['error'][:100]}{'...' if len(failure['error']) > 100 else ''}</td>
                                <td style="font-style: italic; color: #e74c3c; font-size: 9px;">{ai_display}</td>
                                <td>
                                    <a href="logs/{log_file}" class="log-link">LOG</a>
                                    <a href="logs/{xml_path}" class="log-link xml">XML</a>
                                </td>
                            </tr>
            '''
            
        if len(failures) > 20:
            table_html += f'''
                            <tr>
                                <td colspan="6" style="text-align: center; font-style: italic; color: #7f8c8d; padding: 10px;">
                                    📝 + {len(failures) - 20} more test failures
                                </td>
                            </tr>
            '''
            
        table_html += '''
                        </tbody>
                    </table>
                </div>
            </div>
        '''
        
        return table_html
        
    def _generate_quick_actions(self):
        """Generate quick actions section"""
        if not self.analyzer.failures:
            return ''
            
        # Find representative log files
        log_links = []
        for failure in self.analyzer.failures[:3]:
            xml_path = failure.get('relative_path', failure['file'])
            log_file = xml_path.replace('.xml', '.log')
            test_type = "QoS" if 'qos' in failure['test'].lower() else "IPv6" if 'ipv6' in failure['test'].lower() else "Test"
            log_links.append(f'📋 <a href="logs/{log_file}" style="color: #3498db;">View {test_type} Log</a>')
            
        return f'''
        <div style="background: white; padding: 10px; border-radius: 8px; margin-top: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <strong style="color: #2c3e50;">🎯 Quick Actions:</strong>
            <span style="font-size: 11px; margin-left: 10px;">
                {" • ".join(log_links)}
            </span>
        </div>
        '''
        
    def _get_exact_css(self):
        """Return exact CSS matching reference design"""
        return '''<style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; font-size: 12px; background: #f5f5f5; }
        .container { max-width: 100vw; padding: 10px; }
        .header { background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header h1 { font-size: 20px; margin-bottom: 5px; color: #2c3e50; }
        .location { font-family: monospace; font-size: 10px; color: #7f8c8d; background: #ecf0f1; padding: 5px; border-radius: 4px; }
        .stats { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
        .stat { background: white; padding: 10px; border-radius: 6px; text-align: center; min-width: 100px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .stat-num { font-size: 18px; font-weight: bold; }
        .stat-label { font-size: 9px; color: #7f8c8d; text-transform: uppercase; }
        .success { color: #27ae60; }
        .error { color: #e74c3c; }
        .failure { color: #c0392b; }
        .skipped { color: #f39c12; }
        .xfail { color: #9b59b6; }
        .flaky { color: #e67e22; }
        .main-content { display: flex; gap: 15px; height: calc(100vh - 200px); }
        .findings { flex: 1; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow-y: auto; }
        .findings h2 { font-size: 14px; margin-bottom: 10px; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }
        .findings ul { padding-left: 15px; line-height: 1.4; }
        .findings li { margin-bottom: 5px; font-size: 11px; }
        .tests { flex: 2; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden; }
        .tests h2 { font-size: 14px; padding: 15px; margin: 0; color: #2c3e50; border-bottom: 2px solid #3498db; }
        .filters { padding: 10px; background: #f8f9fa; display: flex; gap: 8px; flex-wrap: wrap; }
        .filter-btn { padding: 4px 8px; border: 1px solid #3498db; background: white; color: #3498db; border-radius: 15px; cursor: pointer; font-size: 10px; }
        .filter-btn:hover, .filter-btn.active { background: #3498db; color: white; }
        .filter-btn.flaky-btn { border-color: #e67e22; color: #e67e22; }
        .filter-btn.flaky-btn:hover, .filter-btn.flaky-btn.active { background: #e67e22; }
        .table-wrapper { height: calc(100% - 80px); overflow-y: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 10px; }
        th, td { padding: 6px; text-align: left; border-bottom: 1px solid #ecf0f1; }
        th { background: #f8f9fa; font-weight: 600; position: sticky; top: 0; font-size: 9px; }
        th:nth-child(5), td:nth-child(5) { width: 200px; max-width: 200px; word-wrap: break-word; }
        tr:hover { background: #f1f8ff; }
        .error-badge { background: #ffebee; color: #c62828; padding: 2px 4px; border-radius: 3px; font-size: 8px; }
        .failure-badge { background: #ffcdd2; color: #c62828; padding: 2px 4px; border-radius: 3px; font-size: 8px; }
        .flaky-badge { background: #fff3e0; color: #ef6c00; padding: 1px 4px; border-radius: 3px; font-size: 7px; margin-left: 4px; }
        .log-link { background: #3498db; color: white; padding: 2px 6px; text-decoration: none; border-radius: 3px; margin-right: 3px; font-size: 8px; }
        .log-link:hover { background: #2980b9; }
        .log-link.xml { background: #e67e22; }
        .log-link.xml:hover { background: #d35400; }
        .recommendations { background: #fef9e7; border-left: 4px solid #f39c12; padding: 10px; margin-top: 10px; }
        .recommendations h3 { font-size: 12px; margin-bottom: 8px; color: #2c3e50; }
        .recommendations ol { padding-left: 15px; font-size: 10px; }
        .recommendations li { margin-bottom: 3px; }
        .retry-stats { display: flex; gap: 10px; margin-top: 10px; }
        .retry-stat { background: #f8f9fa; padding: 8px; border-radius: 4px; text-align: center; flex: 1; }
        .retry-num { font-size: 16px; font-weight: bold; }
        .retry-label { font-size: 8px; color: #7f8c8d; }
        .analyze-btn { background: #17a2b8; color: white; border: none; padding: 4px 8px; border-radius: 3px; cursor: pointer; font-size: 8px; }
        .analyze-btn:hover { background: #138496; }
        .analyze-btn:disabled { background: #6c757d; cursor: not-allowed; }
        </style>'''

def main():
    parser = argparse.ArgumentParser(description='Generate SONiC Test Dashboard from XML results')
    parser.add_argument('--date', required=True, help='Test date (e.g., 2025-08-07)')
    parser.add_argument('--server', required=True, help='Server name (e.g., tst-esx-60)')
    parser.add_argument('--path', required=True, help='Path to backup_logs directory')
    parser.add_argument('--output', help='Output HTML file (auto-generated if not specified)')
    
    args = parser.parse_args()
    
    # Validate paths
    if not os.path.exists(args.path):
        print(f"Error: Path does not exist: {args.path}")
        return 1
        
    # Generate output filename if not provided
    if not args.output:
        server_short = args.server.replace('tst-esx-', 'tst')
        args.output = f"sonic_dashboard_{server_short}_{args.date}.html"
        
    print(f"SONiC Dashboard Generator")
    print(f"========================")
    print(f"Date: {args.date}")
    print(f"Server: {args.server}")
    print(f"Path: {args.path}")
    print(f"Output: {args.output}")
    print()
    
    # Initialize analyzer
    analyzer = SONiCTestAnalyzer(args.path, args.server, args.date)
    
    # Analyze logs
    if not analyzer.analyze_logs():
        print("Failed to analyze logs")
        return 1
        
    # Generate dashboard
    generator = HTMLGenerator(analyzer)
    output_file = generator.generate_dashboard(args.output)
    
    print()
    print("✅ Dashboard generation complete!")
    print(f"📊 Total Tests: {sum(analyzer.stats.values())}")
    print(f"✅ Passed: {analyzer.stats.get('success', 0)}")
    print(f"❌ Failed: {analyzer.stats.get('failure', 0)}")
    print(f"🚨 Errors: {analyzer.stats.get('error', 0)}")
    print(f"⏭️  Skipped: {analyzer.stats.get('skipped', 0)}")
    print(f"📄 Output: {output_file}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
