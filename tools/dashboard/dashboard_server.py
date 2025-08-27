#!/usr/bin/env python3
"""
SONiC Dashboard Management Server
Provides API endpoints for dashboard generation and management
"""

import os
import sys
import json
import glob
import subprocess
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.parse

class DashboardHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == '/api/dashboards':
            self.handle_list_dashboards()
        elif parsed_url.path == '/api/health':
            self.send_json_response({'status': 'ok', 'service': 'SONiC Dashboard API'})
        elif parsed_url.path.startswith('/dashboards/'):
            self.handle_dashboard_file(parsed_url.path)
        else:
            self.send_error(404, "Endpoint not found")
            
    def do_POST(self):
        """Handle POST requests"""
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == '/api/generate':
            self.handle_generate_dashboard(parsed_url)
        else:
            self.send_error(404, "Endpoint not found")
            
    def handle_list_dashboards(self):
        """List available dashboards"""
        try:
            dashboards = []
            dashboard_dir = os.path.join(os.getcwd(), 'dashboards')
            
            if os.path.exists(dashboard_dir):
                # Find all HTML files in dashboard directories
                pattern = os.path.join(dashboard_dir, '**/sonic_dashboard_*.html')
                dashboard_files = glob.glob(pattern, recursive=True)
                
                for file_path in dashboard_files:
                    try:
                        # Extract info from filename
                        filename = os.path.basename(file_path)
                        # Expected format: sonic_dashboard_tst60_2025-08-07.html
                        parts = filename.replace('sonic_dashboard_', '').replace('.html', '').split('_')
                        if len(parts) >= 2:
                            server = parts[0]
                            date = parts[1]
                            
                            # Get relative URL
                            rel_path = os.path.relpath(file_path, os.getcwd())
                            
                            # Get basic stats from file (if possible)
                            stats = self.get_dashboard_stats(file_path)
                            
                            dashboards.append({
                                'date': date,
                                'server': server,
                                'url': rel_path,
                                'stats': stats,
                                'file_size': os.path.getsize(file_path),
                                'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M')
                            })
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")
                        
                # Sort by date descending
                dashboards.sort(key=lambda x: x['date'], reverse=True)
                
            self.send_json_response(dashboards)
            
        except Exception as e:
            self.send_error(500, f"Failed to list dashboards: {str(e)}")
            
    def get_dashboard_stats(self, file_path):
        """Extract basic stats from dashboard HTML file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Simple regex to extract stats from HTML
            import re
            
            # Look for stat numbers in the HTML
            total_match = re.search(r'<div class="stat-num">(\d+,?\d*)</div>\s*<div class="stat-label">Total</div>', content)
            success_match = re.search(r'<div class="stat-num success">(\d+,?\d*)</div>', content)
            
            if total_match and success_match:
                total = total_match.group(1)
                success = success_match.group(1)
                return f"{total} total, {success} passed"
            else:
                return "Stats not available"
                
        except Exception:
            return "Stats not available"
            
    def handle_dashboard_file(self, path):
        """Serve dashboard files"""
        try:
            file_path = os.path.join(os.getcwd(), path.lstrip('/'))
            
            if os.path.exists(file_path) and file_path.endswith('.html'):
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Dashboard not found")
                
        except Exception as e:
            self.send_error(500, f"Error serving file: {str(e)}")
            
    def handle_generate_dashboard(self, parsed_url):
        """Handle dashboard generation request"""
        try:
            # Parse query parameters
            params = parse_qs(parsed_url.query)
            date = params.get('date', [None])[0]
            
            if not date:
                self.send_error(400, "Missing required parameter: date")
                return
                
            # Start generation in background thread
            thread = threading.Thread(
                target=self.generate_dashboard_async, 
                args=(date,)
            )
            thread.daemon = True
            thread.start()
            
            self.send_json_response({
                'status': 'started',
                'message': f'Dashboard generation started for {date}',
                'date': date
            })
            
        except Exception as e:
            self.send_error(500, f"Generation failed: {str(e)}")
            
    def generate_dashboard_async(self, date):
        """Generate dashboard in background"""
        try:
            print(f"Starting background generation for {date}")
            
            # List of servers to check
            servers = ['tst-esx-60', 'tst-esx-61', 'tst-esx-62']
            
            for server in servers:
                try:
                    print(f"Checking {server} for {date} data...")
                    
                    # Check if data exists on server
                    check_cmd = f'ssh sonic@{server} "ls /home/sonic/202505/{date}/sonic-mgmt/backup_logs/ 2>/dev/null"'
                    result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        print(f"Data found on {server}, generating dashboard...")
                        
                        # Generate dashboard
                        server_short = server.replace('tst-esx-', 'tst')
                        output_file = f'dashboards/{date}/sonic_dashboard_{server_short}_{date}.html'
                        
                        # Create output directory
                        os.makedirs(f'dashboards/{date}', exist_ok=True)
                        
                        # Run dashboard generator
                        gen_cmd = f'''ssh sonic@{server} "cd /tmp && python3 sonic_dashboard_generator.py \\
                            --date {date} \\
                            --server {server} \\
                            --path /home/sonic/202505/{date}/sonic-mgmt/backup_logs \\
                            --output sonic_dashboard_{server_short}_{date}.html"'''
                        
                        gen_result = subprocess.run(gen_cmd, shell=True, capture_output=True, text=True)
                        
                        if gen_result.returncode == 0:
                            # Copy dashboard from server
                            copy_cmd = f'scp sonic@{server}:/tmp/sonic_dashboard_{server_short}_{date}.html {output_file}'
                            copy_result = subprocess.run(copy_cmd, shell=True, capture_output=True, text=True)
                            
                            if copy_result.returncode == 0:
                                print(f"Dashboard generated successfully: {output_file}")
                            else:
                                print(f"Failed to copy dashboard from {server}: {copy_result.stderr}")
                        else:
                            print(f"Dashboard generation failed on {server}: {gen_result.stderr}")
                    else:
                        print(f"No data found on {server} for {date}")
                        
                except Exception as e:
                    print(f"Error processing {server}: {e}")
                    
        except Exception as e:
            print(f"Background generation error: {e}")
            
    def send_json_response(self, data, status_code=200):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())
        
    def log_message(self, format, *args):
        """Custom log message format"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")

def main():
    """Start the dashboard management server"""
    port = 8082
    server_address = ('', port)
    
    print(f"SONiC Dashboard Management Server")
    print(f"=================================")
    print(f"Starting on port {port}")
    print(f"Dashboard directory: {os.path.join(os.getcwd(), 'dashboards')}")
    print(f"")
    print(f"Available endpoints:")
    print(f"  GET  /api/dashboards       - List available dashboards")
    print(f"  POST /api/generate?date=X  - Generate dashboard for date")
    print(f"  GET  /api/health           - Health check")
    print(f"  GET  /dashboards/*         - Serve dashboard files")
    print(f"")
    print(f"Access portal: http://localhost:{port}/index.html")
    print()
    
    # Ensure directories exist
    os.makedirs('dashboards', exist_ok=True)
    
    try:
        httpd = HTTPServer(server_address, DashboardHandler)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\\nShutting down server...")
        httpd.shutdown()
    except Exception as e:
        print(f"Server error: {e}")

if __name__ == "__main__":
    main()
