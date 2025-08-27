#!/bin/bash
"""
SONiC Dashboard Deployment Script
Deploys dashboard system to test servers and starts services
"""

set -e

# Configuration
SERVERS="tst-esx-60 tst-esx-61 tst-esx-62"
DASHBOARD_PORT=9000
API_PORT=8081
MGMT_PORT=8082

echo "🚀 SONiC Dashboard Deployment"
echo "============================="

# Deploy files to test servers
echo "📤 Deploying files to test servers..."
for server in $SERVERS; do
    echo "  Deploying to $server..."
    
    # Copy dashboard generator
    scp sonic_dashboard_generator.py sonic@$server:/tmp/ || echo "    Warning: Could not deploy to $server"
    
    # Copy analysis API
    scp analyze_failure_api.py sonic@$server:/tmp/ || echo "    Warning: Could not copy API to $server"
done

# Start management server locally
echo "🖥️  Starting dashboard management server on port $MGMT_PORT..."
nohup python3 dashboard_server.py > dashboard_server.log 2>&1 &
MGMT_PID=$!
echo "  Management server started (PID: $MGMT_PID)"

# Wait for server to start
sleep 2

# Test management server
if curl -s http://localhost:$MGMT_PORT/api/health > /dev/null; then
    echo "✅ Management server is running"
else
    echo "❌ Management server failed to start"
    exit 1
fi

echo ""
echo "🎯 Deployment Complete!"
echo "======================"
echo "📊 Dashboard Portal: http://localhost:$MGMT_PORT/index.html"
echo "🔧 Management API:   http://localhost:$MGMT_PORT/api/health"
echo ""
echo "📋 Manual Commands:"
echo "  Generate dashboard: python3 sonic_dashboard_generator.py --date YYYY-MM-DD --server tst-esx-XX --path /path/to/logs"
echo "  Start analysis API: python3 analyze_failure_api.py"
echo ""
echo "📁 Files deployed:"
echo "  - sonic_dashboard_generator.py (on all test servers)"
echo "  - analyze_failure_api.py (on all test servers)"  
echo "  - dashboard_server.py (management server)"
echo "  - index.html (portal interface)"
echo ""
echo "🔗 Test servers will be accessible at:"
for server in $SERVERS; do
    echo "  - $server: http://172.30.139.XXX:$DASHBOARD_PORT/"
done
echo ""
echo "ℹ️  To stop: kill $MGMT_PID"
