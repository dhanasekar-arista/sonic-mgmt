# SONiC Test Dashboard System

Automated dashboard generation and analysis system for SONiC test results.

## 🚀 Quick Start

```bash
# Deploy the entire system
cd tools/dashboard
./deploy.sh

# Access the dashboard portal
open http://localhost:8082/index.html
```

## 📊 Features

### Dashboard Generation
- **Automatic Analysis:** Analyzes XML test results and generates HTML dashboards
- **AI-Powered Insights:** Root cause analysis for test failures
- **Interactive Interface:** Filterable tables, clickable log links
- **Multi-Server Support:** Works across all test servers (tst-esx-60, 61, 62)

### On-Demand Analysis
- **Smart Performance:** Auto-analyzes top 5 failures, on-demand for others
- **Detailed Reports:** Full analysis files with troubleshooting steps
- **Real-time API:** HTTP endpoint for interactive failure analysis

### Portal Interface
- **Date Selection:** Pick any test date and view/generate dashboards
- **Auto-Discovery:** Automatically finds existing dashboards
- **Generation Control:** Trigger new dashboard creation with one click

## 🛠️ Components

### Core Files
- **`sonic_dashboard_generator.py`** - Main dashboard generation engine
- **`analyze_failure_api.py`** - On-demand failure analysis API
- **`dashboard_server.py`** - Dashboard management server
- **`index.html`** - Portal interface
- **`deploy.sh`** - Deployment automation script

### Directory Structure
```
tools/dashboard/
├── sonic_dashboard_generator.py    # Dashboard generator
├── analyze_failure_api.py          # Analysis API
├── dashboard_server.py             # Management server
├── index.html                      # Portal interface
├── deploy.sh                       # Deployment script
├── README.md                       # This file
└── dashboards/                     # Generated dashboards
    └── 2025-08-07/                 # Date-based organization
        ├── sonic_dashboard_tst60_2025-08-07.html
        ├── sonic_dashboard_tst61_2025-08-07.html
        └── analysis/                # AI analysis files
            ├── analysis_test_mgmt_ipv6_only.txt
            └── analysis_test_qos_sai.txt
```

## 📋 Usage

### Generate Dashboard (Manual)
```bash
# Single server dashboard
python3 sonic_dashboard_generator.py \
  --date 2025-08-07 \
  --server tst-esx-60 \
  --path /home/sonic/202505/2025-08-07/sonic-mgmt/backup_logs

# Custom output file
python3 sonic_dashboard_generator.py \
  --date 2025-08-07 \
  --server tst-esx-60 \
  --path /path/to/logs \
  --output my_custom_dashboard.html
```

### API Usage
```bash
# Check API health
curl http://localhost:8081/health

# Analyze specific failure
curl "http://localhost:8081/analyze?xml_path=ip/test_mgmt_ipv6_only.xml&test_name=test_bgp_facts_ipv6_only"

# List available dashboards
curl http://localhost:8082/api/dashboards

# Generate dashboard via API
curl -X POST "http://localhost:8082/api/generate?date=2025-08-07"
```

### Portal Usage
1. Open `http://localhost:8082/index.html`
2. Select test date
3. Click "View Dashboard" (if exists) or "Generate New"
4. Dashboard opens with interactive analysis

## 🎯 Dashboard Features

### Summary Section
- **Test Statistics:** Total, passed, failed, errors, skipped
- **Color-coded Cards:** Visual status indicators
- **Key Findings:** Auto-generated insights
- **Priorities:** Recommended action items

### Failed Tests Table  
- **Interactive Filters:** All, Errors, Failures
- **AI Analysis Column:** Root cause analysis for each failure
- **Log Access:** Direct links to LOG and XML files
- **On-Demand Analysis:** Click "🤖 Analyze" for detailed analysis

### Analysis Files
- **Detailed Reports:** Comprehensive analysis with troubleshooting steps
- **Downloadable:** Save analysis files for offline review
- **Searchable:** Easy to find specific failure analyses

## ⚙️ Configuration

### Environment Variables
- `SONIC_DASHBOARD_PORT` - Dashboard HTTP port (default: 9000)
- `SONIC_API_PORT` - Analysis API port (default: 8081)
- `SONIC_MGMT_PORT` - Management server port (default: 8082)

### Server Requirements
- Python 3.6+ with standard libraries
- SSH access to test servers
- Network connectivity between servers

## 🔧 Troubleshooting

### Common Issues
1. **Port conflicts:** Modify port numbers in scripts
2. **SSH access:** Ensure passwordless SSH to test servers
3. **Log file access:** Verify log directory permissions
4. **Large log files:** Script automatically limits analysis to last 2000 lines

### Log Files
- Dashboard generation: Check script output
- API server: `/tmp/analysis_api.log`
- Management server: `dashboard_server.log`

## 🚀 Advanced Usage

### Custom Analysis
Modify `_basic_failure_analysis()` method in `sonic_dashboard_generator.py` to add custom failure pattern detection.

### Multi-Server Deployment
Use `deploy.sh` to automatically deploy to all test servers and start required services.

### Integration
The system is designed to integrate with existing SONiC test infrastructure and can be extended for CI/CD pipelines.

## 📞 Support

For issues or feature requests:
1. Check existing dashboards for similar patterns
2. Review log files for error details  
3. Refer to AGENTS.md for SONiC testing guidelines
4. Use the AI analysis features for automated troubleshooting

---
Generated by SONiC Dashboard System | Last updated: $(date)
