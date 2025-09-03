# SONiC Gerrit AI Automation Tool

**🤖 AI-Powered Code Review and PR Creation for SONiC Gerrit Changes**

## Overview

`gerrit_ai_automated.py` provides fully automated, AI-powered code review for any SONiC Gerrit change with:

- **Real AI Analysis**: Oracle AI or Gemini API integration
- **Smart Scoring**: AI determines +1/0/-1 based on functional analysis
- **Generic Operation**: Works with any Gerrit change ID (no hardcoding)
- **Draft PR Creation**: Automatic upstream GitHub PR generation
- **Gerrit Integration**: Posts AI analysis and PR status to Gerrit

## Prerequisites

### 1. AI Service Setup

**Oracle AI (Recommended):**
```bash
npm install -g @sourcegraph/amp
amp login  # One-time setup
```

**Gemini AI (Alternative):**
- Get API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

### 2. Gerrit Access
```bash
# Generate HTTP credentials at: https://gerrit.corp.arista.io/settings/#HTTPCredentials
# Create gerrit_config.json:
{
  "gerrit_url": "https://gerrit.corp.arista.io",
  "username": "your_username", 
  "password": "your_http_password",
  "github_token": "your_github_token"
}
```

### 3. Dependencies
```bash
pip3 install requests
```

## Usage

### Basic AI Review
```bash
# Oracle AI analysis
python3 gerrit_ai_automated.py --change-id 459604 --config gerrit_config.json --ai-provider oracle --submit

# Gemini AI analysis  
python3 gerrit_ai_automated.py --change-id 459604 --ai-provider gemini --api-key YOUR_GEMINI_KEY --submit
```

### Full Automation (AI + PRs)
```bash
# Oracle AI + create draft PRs
python3 gerrit_ai_automated.py --change-id 459604 --config gerrit_config.json --ai-provider oracle --create-prs --submit

# Just analyze (no submission)
python3 gerrit_ai_automated.py --change-id 459604 --config gerrit_config.json --ai-provider oracle
```

## Command Options

| Option | Description | Required |
|--------|-------------|----------|
| `--change-id` | Gerrit change number | ✅ Yes |
| `--config` | Config file path | No (default: gerrit_config.json) |
| `--ai-provider` | `oracle` or `gemini` | No (default: oracle) |
| `--api-key` | API key for Gemini | Only for Gemini |
| `--submit` | Submit review to Gerrit | No |
| `--create-prs` | Create draft PRs | No |
| `--github-token` | GitHub token | Only for PRs |

## AI Providers Comparison

| Feature | Oracle AI | Gemini AI |
|---------|-----------|-----------|
| **Setup** | `amp login` | API key required |
| **Cost** | Included with Amp | Pay-per-use |
| **Quality** | Advanced reasoning | Fast analysis |
| **SONiC Knowledge** | SONiC-specific | General purpose |
| **Speed** | Moderate | Fast |

## Example Output

### Successful Review (Score +1)
```
🤖 ORACLE AI-Powered SONiC Review

🔮 Oracle AI Analysis:

PATCH 1 (Enable kdump by default):
• Modifies build_image.sh to add crashkernel memory reservation
• Benefits: Immediate crash debugging without manual setup  
• Recommendation: +1 - Clear debugging improvement

PATCH 2 (Cleanup crashkernel):
• Fixes sonic-kdump-config script bugs and disable functionality
• Recommendation: +1 - Essential cleanup mechanisms

OVERALL: +1 (Approve) - Net positive for crash debugging
```

### Failed Review (Score -1)
```
🤖 ORACLE AI-Powered SONiC Review

🔮 Oracle AI Analysis:

PATCH 0 (improve_build_image): ❌ CRITICAL
• Adds literal shell command that breaks builds
• Missing # comment marker

PATCH 1 (fix): ❌ CRITICAL
• Removes mandatory AC_INIT from configure.ac
• Makes sonic-swss uncompilable

🚨 Verdict: -1 REJECT ALL - Patches break functionality
```

## Integration

### Jenkins Pipeline
```groovy
pipeline {
    environment {
        GH_TOKEN = credentials('github-pat')
    }
    stages {
        stage('AI Review') {
            steps {
                sh """
                    python3 tools/gerrit-automation/gerrit_ai_automated.py \
                        --change-id ${GERRIT_CHANGE_NUMBER} \
                        --config tools/gerrit-automation/gerrit_config.json \
                        --ai-provider oracle \
                        --submit --create-prs \
                        --github-token ${GH_TOKEN}
                """
            }
        }
    }
}
```

### Gerrit Trigger
Configure Gerrit to auto-trigger on comment: `"AI-Review"`

## Troubleshooting

### Oracle AI Issues
```bash
# Check amp CLI installation
which amp

# Test Oracle access
echo "Test oracle connection" | amp -x

# Re-login if needed
amp logout && amp login
```

### Gemini API Issues  
```bash
# Verify API key
curl -H "Content-Type: application/json" \
  "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_API_KEY"
```

### Gerrit Authentication
```bash
# Test Gerrit access
curl -u "username:password" https://gerrit.corp.arista.io/a/accounts/self
```

## Files Created

The tool automatically creates temporary patch files in `/tmp/`:
- `/tmp/patch_<changeid>_<n>_<patchname>.patch`

These are used for AI analysis and automatically cleaned up.
