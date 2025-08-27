#!/usr/bin/env python3
"""
On-Demand SONiC Test Failure Analysis API
Provides HTTP endpoint for analyzing individual test failures
"""

import os
import sys
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.parse

# Import the analysis methods from main script
sys.path.append(os.path.dirname(__file__))
from sonic_dashboard_generator import SONiCTestAnalyzer

class FailureAnalysisHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests for failure analysis"""
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == '/analyze':
            self.handle_analyze_request(parsed_url)
        elif parsed_url.path == '/health':
            self.send_json_response({'status': 'ok', 'service': 'SONiC Failure Analysis API'})
        else:
            self.send_error(404, "Endpoint not found")
            
    def handle_analyze_request(self, parsed_url):
        """Handle failure analysis request"""
        try:
            # Parse query parameters
            params = parse_qs(parsed_url.query)
            xml_path = params.get('xml_path', [None])[0]
            test_name = params.get('test_name', [None])[0]
            logs_base = params.get('logs_base', ['/tmp/logs'])[0]
            
            if not xml_path or not test_name:
                self.send_error(400, "Missing required parameters: xml_path, test_name")
                return
                
            # Decode URL-encoded parameters
            xml_path = urllib.parse.unquote(xml_path)
            test_name = urllib.parse.unquote(test_name)
            
            # Perform analysis
            result = self.analyze_single_failure(xml_path, test_name, logs_base)
            self.send_json_response(result)
            
        except Exception as e:
            self.send_error(500, f"Analysis failed: {str(e)}")
            
    def analyze_single_failure(self, xml_path, test_name, logs_base):
        """Analyze a single failure"""
        try:
            # Create mock failure object
            failure = {
                'file': os.path.basename(xml_path),
                'relative_path': xml_path,
                'test': test_name,
                'type': 'error',  # Default to error
                'error': 'On-demand analysis requested'
            }
            
            # Get log file path
            log_path = xml_path.replace('.xml', '.log')
            full_log_path = os.path.join(logs_base, log_path)
            
            if os.path.exists(full_log_path):
                # Read log content
                with open(full_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    if len(lines) > 2000:
                        log_content = ''.join(lines[-2000:])
                    else:
                        log_content = ''.join(lines)
                        
                # Use analyzer's analysis method
                analyzer = SONiCTestAnalyzer('', '', '')
                short_analysis, detailed_analysis = analyzer._basic_failure_analysis(failure, log_content)
                
                # Save detailed analysis to file
                analysis_filename = f"analysis_{failure['file'].replace('.xml', '')}_ondemand.txt"
                analysis_dir = '/tmp/analysis'
                os.makedirs(analysis_dir, exist_ok=True)
                analysis_filepath = os.path.join(analysis_dir, analysis_filename)
                
                with open(analysis_filepath, 'w', encoding='utf-8') as af:
                    af.write(f"SONiC Test Failure Analysis (On-Demand)\\n")
                    af.write(f"=" * 50 + "\\n\\n")
                    af.write(f"Test: {test_name}\\n")
                    af.write(f"File: {xml_path}\\n")
                    af.write(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n\\n")
                    af.write(f"AI Analysis:\\n{detailed_analysis}\\n\\n")
                    af.write(f"Log Content (last 1500 chars):\\n")
                    af.write("-" * 30 + "\\n")
                    af.write(log_content[-1500:])
                
                return {
                    'status': 'success',
                    'short_analysis': short_analysis,
                    'detailed_analysis': detailed_analysis,
                    'analysis_file': analysis_filename,
                    'log_file_found': True
                }
            else:
                return {
                    'status': 'warning',
                    'short_analysis': 'Root cause: Log file not found - cannot perform detailed analysis',
                    'detailed_analysis': f'Log file not found at: {full_log_path}',
                    'analysis_file': None,
                    'log_file_found': False
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'short_analysis': f'Analysis failed: {str(e)[:50]}',
                'detailed_analysis': f'Error during analysis: {str(e)}',
                'analysis_file': None,
                'log_file_found': False
            }
            
    def send_json_response(self, data, status_code=200):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')  # Allow CORS
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())
        
    def log_message(self, format, *args):
        """Custom log message format"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")

def main():
    """Start the analysis API server"""
    port = 8081
    server_address = ('', port)
    
    print(f"Starting SONiC Failure Analysis API on port {port}")
    print(f"Available endpoints:")
    print(f"  GET /analyze?xml_path=<path>&test_name=<name>&logs_base=<base>")
    print(f"  GET /health")
    print(f"\\nExample usage:")
    print(f"  curl 'http://localhost:{port}/analyze?xml_path=ip/test_mgmt_ipv6_only.xml&test_name=test_bgp_facts_ipv6_only'")
    print()
    
    try:
        httpd = HTTPServer(server_address, FailureAnalysisHandler)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\\nShutting down server...")
        httpd.shutdown()

if __name__ == "__main__":
    main()
