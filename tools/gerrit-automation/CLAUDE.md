# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Recent Updates (2025-10-17)

### Major Changes
1. **Gemini 2.5 Flash Integration** - Upgraded to latest Gemini model via Vertex AI
2. **AI-Powered Conflict Resolution** - Automatic patch conflict resolution using Gemini
3. **Branch-Only Mode** - Script now creates branches without auto-creating PRs (manual PR workflow)
4. **Resume Functionality** - Can resume processing after manual intervention
5. **Conservative Scoring** - Updated AI to only give -1 for compilation errors or 100% wrong code

### Breaking Changes
- `gerrit_to_pr.py` no longer creates PRs automatically - only pushes branches to fork
- Users must manually create PRs from GitHub UI after branches are pushed

## Project Overview

This is a **Gerrit AI Automation Tool** for SONiC (Software for Open Networking in the Cloud) development. The tool provides AI-powered code review and automated GitHub branch creation for Gerrit changes.

## Core Architecture

### Main Components

1. **`gerrit_ai_automated.py`** - Primary automation script that:
   - Fetches Gerrit changes and extracts patch files
   - Performs AI analysis using Oracle AI or Gemini via Vertex AI
   - Assigns code review scores (-1, 0, +1) based on AI analysis
   - Submits reviews to Gerrit with AI feedback
   - Optionally creates draft GitHub PRs

2. **`gerrit_to_pr.py`** - GitHub branch creation module that:
   - Converts Gerrit patches to GitHub branches in your fork
   - Handles repository mapping and branch targeting
   - Supports AI-powered patch conflict resolution
   - Supports multi-repository patch sets
   - **NOTE**: Currently configured to create branches only (no automatic PR creation)

3. **`test_gemini_api.py`** - Diagnostic utility for Gemini API troubleshooting

### AI Provider Architecture

The tool supports two AI providers with failover logic:

- **Oracle AI** (Default): Uses `amp` CLI for SONiC-specific analysis
- **Gemini AI**: Uses Google Cloud Vertex AI for Gemini model access
  - Primary model: `gemini-2.5-flash` (latest)
  - Fallback models: `gemini-2.0-flash-exp`, `gemini-1.5-flash-002`
  - Location: `us-east5` (configurable via CLOUD_ML_REGION)

### AI Scoring Guidelines

The AI follows conservative scoring criteria:
- **+1 (Approve)**: Code is technically correct and improves the system
- **0 (Neutral)**: Minor issues or improvements needed, but not blocking
- **-1 (Request Changes)**: Only given for:
  - Trivial compilation errors (syntax errors, missing imports)
  - Code that is 100% wrong or would break core functionality

This ensures -1 scores are reserved for clear, objective issues rather than subjective concerns.

## Common Development Commands

### Basic AI Review
```bash
# Oracle AI analysis and submission
python3 gerrit_ai_automated.py --change-id 459604 --config gerrit_config.json --ai-provider oracle --submit

# Gemini AI via Vertex AI analysis only (no submission)
python3 gerrit_ai_automated.py --change-id 459604 --ai-provider gemini --gcp-project YOUR_GCP_PROJECT --gcp-location us-east5

# Full automation: AI review + draft PRs
python3 gerrit_ai_automated.py --change-id 459604 --config gerrit_config.json --ai-provider oracle --create-prs --submit
```

### GitHub Branch Creation (Manual PR workflow)
```bash
# Create branches in your fork (no automatic PR creation)
python3 gerrit_to_pr.py --change 509300 --token $GH_TOKEN --config gerrit_config.json

# With AI-powered conflict resolution
python3 gerrit_to_pr.py --change 509300 --token $GH_TOKEN --config gerrit_config.json --ai-resolve --gcp-project YOUR_PROJECT

# Interactive mode - pause on conflicts for manual resolution
python3 gerrit_to_pr.py --change 509300 --token $GH_TOKEN --config gerrit_config.json --interactive

# Resume after manual conflict resolution
python3 gerrit_to_pr.py --change 509300 --token $GH_TOKEN --config gerrit_config.json --resume

# Dry run to see what would be processed
python3 gerrit_to_pr.py --change 509300 --token $GH_TOKEN --dry-run
```

**Workflow**:
1. Script creates branches like `gerrit-509300-sonic-swss-master` in your fork
2. Branches are ready for PR creation
3. Manually create PRs from GitHub UI when ready

### Installation
```bash
# Install Python dependencies
pip install -r requirements.txt

# Set up Google Cloud authentication for Vertex AI (if using Gemini)
gcloud auth application-default login
```

## Configuration Requirements

### Required Files

1. **`gerrit_config.json`** - Gerrit and GitHub credentials:
```json
{
  "gerrit_url": "https://gerrit.corp.arista.io",
  "username": "your_username",
  "password": "your_http_password",
  "github_token": "your_github_token"
}
```

### Environment Setup

**Oracle AI Prerequisites:**
```bash
npm install -g @sourcegraph/amp
amp login  # One-time authentication
```

**Vertex AI Prerequisites (for Gemini):**
```bash
# Install Google Cloud SDK
# See: https://cloud.google.com/sdk/docs/install

# Authenticate with Google Cloud
gcloud auth application-default login

# Set your GCP project (optional, can also pass via --gcp-project)
export GOOGLE_CLOUD_PROJECT=your-project-id

# Set region (optional, defaults to us-east5)
export CLOUD_ML_REGION=us-east5
```

**GitHub Repository Forks:**
- Must fork SONiC repositories before PR creation
- Supported repos: sonic-buildimage, sonic-utilities, sonic-mgmt, sonic-swss

## Key Workflow Integration

### Patch Processing Pipeline
1. **Extract**: Download patch files from Gerrit change
2. **Analyze**: AI analysis of functional impact and technical correctness
3. **Score**: Automatic scoring (+1/0/-1) based on AI assessment
4. **Submit**: Post AI review to Gerrit with score
5. **Create Branches**: Push branches to your fork for manual PR creation

### Patch Application Strategy

The tool uses a multi-tier fallback approach for applying patches:

1. **`git am`** - Preserves commit messages and metadata (preferred)
2. **`git apply`** - Falls back if git am fails (SHA1 mismatches)
3. **AI Resolution** - Uses Gemini 2.5 Flash to intelligently resolve conflicts
   - Analyzes patch intent and current code state
   - Merges changes without losing functionality
   - Handles line number mismatches automatically
4. **Interactive Mode** - Pauses for manual resolution if all automated methods fail

**AI Conflict Resolution** (with `--ai-resolve` flag):
- Reads patch and current file states
- Uses Gemini to understand intent of both
- Generates complete updated file content
- Commits with "(Applied with AI assistance)" note

### Repository Mapping Logic
- Patches are mapped to target repositories based on file path structure: `patches/<branch>/<repo>/<patch-name>`
- Supports branch-specific targeting (not always master)
- Groups patches by repository for consolidated PRs

## Error Handling and Diagnostics

### Common Issue Patterns

**AI Provider Failures:**
- Oracle: Check `amp` CLI installation and authentication
- Gemini (Vertex AI):
  - Verify GCP project ID is correct (use --gcp-project)
  - Ensure Google Cloud authentication is set up (`gcloud auth application-default login`)
  - Check that Vertex AI API is enabled in your GCP project
  - Verify region is supported (default: us-east5)

**GitHub PR Creation Failures:**
- Authentication: Verify GitHub token has repo access
- Repository access: Ensure forks exist and are accessible
- Branch conflicts: Tool handles existing branch scenarios

**Gerrit Authentication:**
- Uses HTTP credentials (not SSH)
- Requires proper permission levels for review submission

## Important Implementation Notes

### AI Analysis Approach
- **Functional Analysis**: Evaluates technical impact on SONiC system components
- **Risk Assessment**: Identifies breaking changes, build failures, or functionality issues
- **Contextual Scoring**: Considers patch complexity and system criticality

### Branch Creation Strategy
- **Manual PR Workflow**: Script creates branches only; PRs created manually via GitHub UI
- **Private Forks**: Pushes branches to user's fork (default: dhanasekar-arista)
- **Branch Naming**: Format `gerrit-{change_id}-{repo}-{target_branch}`
- **Clean Commits**: Removes internal metadata from commit messages
- **Resume Support**: Can resume from working directory after manual fixes

### Temporary File Management
- Patch files stored in `/tmp/patch_<changeid>_<n>_<patchname>.patch`
- Working directories in `/tmp/gerrit-pr-{repo}-{changeid}/` (preserved in interactive mode)
- Automatic cleanup after processing (unless using `--interactive` or `--resume`)

## Advanced Features

### AI-Powered Patch Conflict Resolution

When patches fail to apply with standard git tools, the `--ai-resolve` flag enables intelligent conflict resolution:

```bash
python3 gerrit_to_pr.py --change 509300 --token $GH_TOKEN \
  --config gerrit_config.json \
  --ai-resolve \
  --gcp-project YOUR_GCP_PROJECT
```

**How it works**:
1. Detects patch application failures
2. Reads affected files and patch content
3. Sends to Gemini 2.5 Flash with context about both sides
4. AI generates complete merged file content
5. Applies changes and creates commit

**Success rate**: Handles most line number mismatches and minor merge conflicts automatically.

### Interactive Conflict Resolution

Use `--interactive` for manual control over conflicts:

```bash
python3 gerrit_to_pr.py --change 509300 --token $GH_TOKEN \
  --config gerrit_config.json \
  --interactive
```

**Benefits**:
- Working directory preserved in `/tmp/gerrit-pr-{repo}-{changeid}/`
- Script pauses when conflicts occur
- You can manually fix conflicts and commit
- Use `--resume` to continue processing remaining repos

### Resume Capability

After manual fixes in interactive mode, resume processing:

```bash
python3 gerrit_to_pr.py --change 509300 --token $GH_TOKEN \
  --config gerrit_config.json \
  --resume
```

**Use case**: When one repo has complex conflicts requiring manual intervention, fix it manually then resume to process remaining repos.

## Testing Strategy

### Manual Testing
```bash
# Test Oracle AI with known change ID
python3 gerrit_ai_automated.py --change-id <test_change> --config gerrit_config.json --ai-provider oracle

# Test Gemini via Vertex AI
python3 gerrit_ai_automated.py --change-id <test_change> --config gerrit_config.json --ai-provider gemini --gcp-project <your-project-id>
```

### Integration Testing
- Test with various patch types (build, config, code changes)
- Verify multi-repository patch handling
- Validate AI scoring consistency