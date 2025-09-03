# SONiC Gerrit Automation Tools

Automated code review and upstream PR creation tools for SONiC development workflow.

## 🚀 Features

- **Automated Code Review**: AI-powered analysis of SONiC patches with enhanced diff visualization
- **Upstream PR Creation**: Automatically create GitHub draft PRs from Gerrit changes
- **Gerrit Integration**: Updates Gerrit with review summaries and PR links
- **SONiC-Specific Checks**: Validates test files, coding standards, and patch formats

## 📋 Prerequisites

### Required Python Packages
```bash
pip3 install requests unidiff rich pyyaml
```

### Gerrit Access
1. **HTTP Credentials**: Generate at `https://gerrit.corp.arista.io/settings/#HTTPCredentials`
2. **Configuration**: Create `gerrit_config.json` with your credentials

### GitHub Access (for PR creation)
1. **Personal Access Token**: Generate at `https://github.com/settings/tokens`
2. **Permissions Required**: 
   - ✅ **`repo`** - Required to create branches, push code, and open PRs
   - ✅ **`workflow`** - SONiC repos have GitHub Actions triggered by PRs. Without this permission, PRs might fail to trigger builds/tests
3. **Fork Repositories**: Fork `sonic-net/sonic-buildimage`, `sonic-net/sonic-utilities`, etc.

## 🔧 Setup

### 1. Install Dependencies
```bash
pip3 install -r requirements_gerrit.txt
```

### 2. Configure Gerrit Credentials
```bash
# Create configuration template
python3 gerrit_review_plugin.py --create-config

# Edit gerrit_config.json with your credentials:
{
  "gerrit_url": "https://gerrit.corp.arista.io",
  "username": "your_gerrit_username",
  "password": "your_http_password"
}
```

### 3. Set GitHub Token
```bash
export GH_TOKEN="your_github_token"
```

## 📖 Usage

### Functional Code Review (Recommended)
```bash
# Enhanced functional review with SONiC architecture analysis
python3 gerrit_functional_review.py --change-id 459604 --config gerrit_config.json

# Basic syntax review only
python3 gerrit_review_plugin.py --change-id 459604 --config gerrit_config.json --submit
```

### Review + Create Draft PRs
```bash
# Review + create upstream draft PRs + update Gerrit
python3 gerrit_review_plugin.py --change-id 459604 --config gerrit_config.json --create-prs --github-token $GH_TOKEN

# Or use environment variables for credentials
export GERRIT_USERNAME="your_username"
export GERRIT_PASSWORD="your_password"
python3 gerrit_review_plugin.py --change-id 459604 --create-prs --github-token $GH_TOKEN
```

### Standalone PR Creation
```bash
# Create PRs without review
python3 gerrit_to_pr.py --change 459604 --token $GH_TOKEN --config gerrit_config.json

# Dry run to see what would be created
python3 gerrit_to_pr.py --change 459604 --token $GH_TOKEN --config gerrit_config.json --dry-run
```

## 🎯 Example Output

### Functional Code Review
```
🤖 SONiC Functional Code Review

🔍 Functional Analysis:
- ℹ️ 2 recommendations

### enable_kdump_by_default.patch
build_image.sh (+7/-2 lines)
- Adds crashkernel memory allocation: 0M-2G:256M,2G-4G:320M,4G-8G:384M,8G-:448M
- Fixes FIPS parameter formatting to avoid newline issues

Functional Comments:
- build_image.sh:15 [info] Kernel boot parameter modification detected. Verify crashkernel allocation suits target hardware memory profiles.
```

### Draft PR Creation
```
Found 2 patch files changed in this review:
  - patches/master/sonic-buildimage/enable_kdump_by_default.patch
  - patches/master/sonic-utilities/cleanup_crashkernel_from_kernel_cmdline_append_file.patch

Mapped enable_kdump_by_default.patch → sonic-buildimage
Mapped cleanup_crashkernel_from_kernel_cmdline_append_file.patch → sonic-utilities

✅ Successfully created 2 PRs:
  - https://github.com/sonic-net/sonic-buildimage/pull/XXXX
  - https://github.com/sonic-net/sonic-utilities/pull/YYYY
```

## 📁 Files

- **`gerrit_functional_review.py`** - Enhanced functional review plugin with SONiC architecture awareness
- **`gerrit_review_plugin.py`** - Base code review plugin with diff analysis
- **`gerrit_to_pr.py`** - Standalone script for creating GitHub PRs from Gerrit
- **`sonic_rule_engine.py`** - SONiC knowledge base and functional rule system
- **`gerrit_config.json`** - Configuration template for Gerrit credentials
- **`component_map.yml`** - Maps patch paths to SONiC repositories
- **`requirements_gerrit.txt`** - Python dependencies

## ⚙️ Configuration

### Automatic Repository Detection
The tools automatically detect target repository and branch from patch file paths:

```
patches/<branch-name>/<repo-name>/<patch-name>

Examples:
patches/master/sonic-buildimage/enable_kdump_by_default.patch
→ Creates PR against master branch in sonic-buildimage

patches/msft-202405/sonic-mgmt/add-macsec-test.patch
→ Creates PR against msft-202405 branch in sonic-mgmt
```

### Advanced Options
```bash
# Custom fork organization
export GH_FORK_ORG="your-github-org"

# Custom base branch  
export GH_BASE="master"

# Use environment variables instead of config file
export GERRIT_USERNAME="your_username"
export GERRIT_PASSWORD="your_password"
export GERRIT_URL="https://gerrit.corp.arista.io"
```

## 🔄 Workflow Integration

### Jenkins/CI Integration
Create a Jenkins job triggered by Gerrit comments:

```groovy
pipeline {
    environment {
        GH_TOKEN = credentials('github-pat')
        GERRIT_USERNAME = credentials('gerrit-user').usr
        GERRIT_PASSWORD = credentials('gerrit-user').pwd
    }
    stages {
        stage('Review and Create PRs') {
            steps {
                sh """
                    python3 gerrit_review_plugin.py \
                        --change-id ${GERRIT_CHANGE_NUMBER} \
                        --submit --create-prs \
                        --github-token ${GH_TOKEN}
                """
            }
        }
    }
}
```

### Gerrit Trigger
Configure Gerrit to trigger on comment: `"Create-PRs"`

## 🛡️ Review Criteria

### SONiC Test Files
- ✅ Required imports: `pytest_assert`, `pytest_require`
- ✅ Topology markers: `@pytest.mark.topology`
- ❌ Raw assert statements
- ❌ Uncontrolled print statements

### Patch Files
- ✅ Proper commit messages and authorship
- ✅ SONiC coding conventions
- ✅ Security best practices
- ❌ Hard-coded configuration values

## 🚧 Draft PR Workflow

1. **Internal Review**: Team reviews patches in Gerrit
2. **Create Draft PRs**: Use `--create-prs` flag to create public draft PRs
3. **Internal Testing**: Verify patches work in draft PRs
4. **Mark Ready**: When approved, mark PRs as "Ready for review"
5. **Community Review**: Upstream SONiC community reviews and merges

## 🐛 Troubleshooting

### Authentication Issues
```bash
# Test Gerrit access
curl -u 'username:password' 'https://gerrit.corp.arista.io/a/changes/459604/detail'

# Regenerate HTTP password in Gerrit settings if needed
```

### Missing Dependencies
```bash
# Install missing packages
pip3 install requests unidiff rich pyyaml

# On macOS, you may need:
/Library/Developer/CommandLineTools/usr/bin/python3 -m pip install --upgrade pip
```

### Patch Application Failures
- Ensure patches target the correct repository (check `component_map.yml`)
- Verify patches are based on current upstream master branch
- Manually resolve conflicts if patches don't apply cleanly

## 📞 Support

For issues or feature requests, contact the SONiC development team or create an issue in the sonic-mgmt repository.
