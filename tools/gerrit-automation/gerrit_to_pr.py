#!/usr/bin/env python3
"""
Gerrit to GitHub PR Automation Script

Takes a Gerrit change with upstreamable SONiC patches and creates GitHub PRs
to the appropriate upstream repositories (sonic-net/sonic-buildimage, etc.)

Usage:
    python3 gerrit_to_pr.py --change 459604 --token $GH_TOKEN
    
Environment Variables:
    GERRIT_URL          - Gerrit server URL (default: https://gerrit.corp.arista.io)
    GERRIT_USERNAME     - Gerrit username
    GERRIT_PASSWORD     - Gerrit HTTP password
    GH_FORK_ORG         - GitHub organization for forks (default: aristanetworks)
    GH_BASE             - Base branch name (default: master)
"""

import argparse
import base64
import sys
import json
import os
import re
import requests
import subprocess
import tempfile
import yaml
from pathlib import Path
from typing import Dict, List, Tuple


class GerritToPRConverter:
    """Convert Gerrit changes to GitHub PRs"""

    def __init__(self, gerrit_url: str, username: str, password: str, github_token: str,
                 use_ai_resolution: bool = False, gcp_project: str = None):
        self.gerrit_url = gerrit_url.rstrip('/')
        self.username = username
        self.password = password
        self.github_token = github_token
        self.use_ai_resolution = use_ai_resolution
        self.gcp_project = gcp_project

        # GitHub settings
        self.fork_org = os.getenv('GH_FORK_ORG', 'dhanasekar-arista')
        self.base_branch = os.getenv('GH_BASE', 'master')

        # No component mapping needed - extract from patch path structure
    
    def gerrit_get(self, endpoint: str) -> Dict:
        """Make authenticated GET request to Gerrit API"""
        url = f"{self.gerrit_url}/a{endpoint}"
        print(f"DEBUG: Making request to {url} with user: {self.username}", file=sys.stderr)
        
        # Use the same headers and authentication as curl
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'gerrit-to-pr/1.0'
        }
        
        response = requests.get(url, auth=(self.username, self.password), headers=headers)
        print(f"DEBUG: Response status: {response.status_code}", file=sys.stderr)
        
        if response.status_code == 401:
            print(f"DEBUG: Authentication failed. Check if credentials are correct.", file=sys.stderr)
            print(f"DEBUG: Try this curl command to verify:", file=sys.stderr)
            print(f"curl -u '{self.username}:PASSWORD' '{url}'")
        
        response.raise_for_status()
        
        # Remove Gerrit's magic prefix
        text = response.text
        if text.startswith(")]}'\n"):
            text = text[5:]
        elif text.startswith(")]}' "):
            text = text[5:]
        
        return json.loads(text)
    
    def download_file(self, change_id: str, revision_id: str, file_path: str) -> str:
        """Download file content from Gerrit"""
        import urllib.parse
        encoded_path = urllib.parse.quote(file_path, safe='')
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/files/{encoded_path}/content"
        
        response = requests.get(url, auth=(self.username, self.password))
        response.raise_for_status()
        
        # Try base64 decode first, fallback to plain text
        try:
            body = response.text.lstrip(")]}'\n")
            return base64.b64decode(body + '=' * (-len(body) % 4)).decode('utf-8')
        except Exception:
            return response.text.lstrip(")]}'\n")
    
    def extract_upstreamable_patches(self, series_content: str) -> List[str]:
        """Extract all patches from series file (considering everything as upstreamable for now)"""
        lines = series_content.split('\n')
        all_patches = []
        
        print(f"DEBUG: Analyzing series file with {len(lines)} lines (treating all as upstreamable)", file=sys.stderr)
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Collect all patch files, regardless of section
            if line_stripped and not line_stripped.startswith('#'):
                if line_stripped.endswith('.patch'):
                    all_patches.append(line_stripped)
                    print(f"DEBUG: Found patch: {line_stripped}", file=sys.stderr)
        
        print(f"DEBUG: Total patches found: {len(all_patches)}", file=sys.stderr)
        return all_patches
    
    def parse_patch_path(self, patch_file_path: str) -> Tuple[str, str]:
        """Parse patch file path to extract branch and repository
        
        Expected format: patches/<branch-name>/<repo-name>/<patch-name>
        Example: patches/msft-202405/sonic-mgmt/add-macsec-profile-replace-test.patch
        
        Returns: (branch_name, repo_name)
        """
        path_parts = patch_file_path.split('/')
        
        if len(path_parts) >= 4 and path_parts[0] == 'patches':
            branch_name = path_parts[1]
            repo_name = path_parts[2]
            return branch_name, repo_name
        
        # Fallback for old format
        return 'master', self.determine_target_repo_legacy(patch_file_path)
    
    def determine_target_repo_legacy(self, patch_file_path: str) -> str:
        """Legacy fallback - extract repo from patch content if path parsing fails"""
        print(f"Warning: Failed to parse repo from path: {patch_file_path}")
        return 'sonic-buildimage'  # Safe default
    
    def run_command(self, cmd: List[str], cwd: str = None, capture_output: bool = False) -> subprocess.CompletedProcess:
        """Run shell command with logging"""
        print(f"+ {' '.join(cmd)}" + (f" (cwd: {cwd})" if cwd else ""))

        if capture_output:
            return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
        else:
            return subprocess.run(cmd, cwd=cwd, check=True)

    def ai_resolve_patch(self, patch_content: str, patch_path: str, repo_dir: str) -> bool:
        """Use AI to intelligently apply a patch that failed with git apply"""
        if not self.use_ai_resolution or not self.gcp_project:
            return False

        print("🤖 Attempting AI-powered patch resolution...")

        try:
            from google.cloud import aiplatform
            from vertexai.generative_models import GenerativeModel

            # Parse patch to find affected files
            affected_files = []
            for line in patch_content.split('\n'):
                if line.startswith('--- a/') or line.startswith('+++ b/'):
                    file_path = line.split('/', 1)[1] if '/' in line else ''
                    if file_path and file_path != '/dev/null':
                        affected_files.append(file_path)

            if not affected_files:
                print("❌ Could not identify files from patch")
                return False

            # Read current file contents
            file_contents = {}
            for file_path in set(affected_files):
                full_path = os.path.join(repo_dir, file_path)
                if os.path.exists(full_path):
                    with open(full_path, 'r') as f:
                        file_contents[file_path] = f.read()
                else:
                    file_contents[file_path] = ""  # New file

            # Prepare AI prompt
            prompt = f"""You are helping apply a Git patch that failed with standard tools.

PATCH CONTENT:
{patch_content[:8000]}

CURRENT FILE STATES:
"""
            for file_path, content in file_contents.items():
                prompt += f"\n--- {file_path} ---\n{content[:2000]}\n"

            prompt += """
TASK: Apply the changes from the patch to the current files. Handle any conflicts intelligently by:
1. Understanding the intent of both the patch and current code
2. Merging changes without losing functionality
3. Resolving line number mismatches

OUTPUT: For each modified file, provide the COMPLETE updated file content in this format:
```filename: path/to/file.cpp
<complete file content here>
```

Be precise and ensure the output is valid code.
"""

            # Call Gemini
            aiplatform.init(project=self.gcp_project, location=os.getenv('CLOUD_ML_REGION', 'us-east5'))
            model = GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(
                prompt,
                generation_config={'max_output_tokens': 8192, 'temperature': 0.2}
            )

            if not response.text:
                print("❌ AI returned no response")
                return False

            # Parse AI response and apply changes
            import re
            file_blocks = re.findall(r'```filename:\s*(.+?)\n(.+?)```', response.text, re.DOTALL)

            if not file_blocks:
                print("❌ AI response format not recognized")
                return False

            # Apply AI-generated changes
            for file_path, new_content in file_blocks:
                file_path = file_path.strip()
                full_path = os.path.join(repo_dir, file_path)

                # Ensure directory exists
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                with open(full_path, 'w') as f:
                    f.write(new_content.strip())

                print(f"✅ AI resolved: {file_path}")

            return True

        except Exception as e:
            print(f"❌ AI resolution failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_github_pr(self, repo: str, target_branch: str, feature_branch: str, patches: List[Tuple[str, str]], change_id: str) -> str:
        """Create new GitHub PR (assumes PR doesn't exist - checked earlier)"""

        # Prepare PR data with clean public descriptions
        if len(patches) == 1:
            title = self.extract_subject_from_patch(patches[0][1])
            # Extract description from patch content for body
            body = self.extract_description_from_patch(patches[0][1])
        else:
            title = f"SONiC system improvements"
            body = "This PR includes multiple SONiC system improvements:\n\n"
            for patch_name, patch_content in patches:
                patch_subject = self.extract_subject_from_patch(patch_content)
                body += f"- {patch_subject}\n"

        # Create new PR as draft for internal review
        github_api_url = f"https://api.github.com/repos/sonic-net/{repo}/pulls"
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github+json'
        }

        pr_data = {
            'title': title,
            'head': f'{self.fork_org}:{feature_branch}',
            'base': target_branch,
            'body': body,
            'draft': True
        }

        response = requests.post(github_api_url, headers=headers, json=pr_data)
        response.raise_for_status()

        pr_url = response.json()['html_url']
        return pr_url
    
    def extract_subject_from_patch(self, patch_content: str) -> str:
        """Extract subject line from patch"""
        lines = patch_content.split('\n')
        for line in lines[:10]:
            if line.startswith('Subject:'):
                return line.replace('Subject:', '').strip()
        return "SONiC system improvement"
    
    def extract_description_from_patch(self, patch_content: str) -> str:
        """Extract clean commit description for public PR"""
        lines = patch_content.split('\n')
        
        # Find commit message after Subject line
        description_lines = []
        found_subject = False
        
        for line in lines:
            if line.startswith('Subject:'):
                found_subject = True
                continue
            elif found_subject and (line.strip() == '---' or line.startswith('diff --git')):
                break
            elif found_subject and line.strip():
                # Skip internal metadata
                if not any(skip in line for skip in ['Change-Id:', 'Signed-off-by:', 'From:', 'Date:', 'Arista', 'gerrit']):
                    description_lines.append(line.strip())
        
        description = '\n\n'.join(description_lines).strip()
        if not description:
            description = "This change improves SONiC system functionality."
        
        return description
    
    def process_change(self, change_id: str, dry_run: bool = False, interactive: bool = False, resume: bool = False) -> List[str]:
        """Process a Gerrit change and create GitHub PRs"""
        print(f"Processing Gerrit change {change_id}...")
        
        # Get change details
        change_details = self.gerrit_get(f'/changes/{change_id}/detail')
        
        # Get current revision
        if 'current_revision_number' in change_details:
            revision_id = str(change_details['current_revision_number'])
        else:
            revision_id = 'current'
        
        # Get files in the change
        files_info = self.gerrit_get(f'/changes/{change_id}/revisions/{revision_id}/files')
        
        # Get only patch files that were actually changed in this Gerrit review
        patch_files = [f for f in files_info.keys() if f.endswith('.patch')]
        
        if not patch_files:
            print("No patch files found in this Gerrit change")
            return []
        
        print(f"Found {len(patch_files)} patch files changed in this review:")
        for pf in patch_files:
            print(f"  - {pf}")
        
        # Download patch files and group by target repository
        repo_to_patches = {}
        
        for patch_file in patch_files:
            patch_content = self.download_file(change_id, revision_id, patch_file)
            
            # Parse repository and branch from file path
            target_branch, target_repo = self.parse_patch_path(patch_file)
            
            patch_name = Path(patch_file).name
            
            # Use branch-specific key for grouping
            repo_key = f"{target_repo}:{target_branch}"
            
            if repo_key not in repo_to_patches:
                repo_to_patches[repo_key] = []
            
            repo_to_patches[repo_key].append((patch_name, patch_content))
            print(f"Mapped {patch_name} → {target_repo} (branch: {target_branch})")
        
        if dry_run:
            print("\n🔍 DRY RUN - Would create the following PRs:")
            for repo_key, patches in repo_to_patches.items():
                repo, branch = repo_key.split(':', 1)
                print(f"  {repo} (branch: {branch}): {[p[0] for p in patches]}")
            return []
        
        # Create PRs for each repository
        pr_urls = []

        for repo_key, patches in repo_to_patches.items():
            repo, branch = repo_key.split(':', 1)

            pr_url = self.create_pr_for_repo(repo, branch, patches, change_id, interactive, resume)
            if pr_url:
                pr_urls.append(pr_url)

        return pr_urls
    
    def check_existing_pr(self, repo: str, target_branch: str, feature_branch: str) -> str:
        """Check if PR already exists for this branch"""
        github_api_url = f"https://api.github.com/repos/sonic-net/{repo}/pulls"
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github+json'
        }

        params = {'head': f'{self.fork_org}:{feature_branch}', 'base': target_branch}
        response = requests.get(github_api_url, headers=headers, params=params)

        if response.status_code == 200 and response.json():
            pr_url = response.json()[0]['html_url']
            return pr_url
        return None

    def check_branch_exists_in_fork(self, repo: str, branch_name: str) -> bool:
        """Check if branch exists in fork"""
        try:
            url = f"https://api.github.com/repos/{self.fork_org}/{repo}/branches/{branch_name}"
            headers = {'Authorization': f'token {self.github_token}'}
            response = requests.get(url, headers=headers)
            return response.status_code == 200
        except Exception:
            return False

    def create_pr_for_repo(self, repo: str, target_branch: str, patches: List[Tuple[str, str]], change_id: str, interactive: bool = False, resume: bool = False) -> str:
        """Create and push branch for a specific repository (PR creation disabled)"""
        print(f"\nPreparing branch for {repo} (target branch: {target_branch}) with {len(patches)} patches...")

        # Generate feature branch name
        feature_branch_name = f'gerrit-{change_id}-{repo}-{target_branch}'
        existing_pr = None  # Skip PR check since we're not creating PRs

        # In resume mode, use existing directory if it exists
        if resume:
            tmp_dir = f"/tmp/gerrit-pr-{repo}-{change_id}"
            if not os.path.exists(tmp_dir):
                print(f"⚠️ Resume directory not found: {tmp_dir}")
                print(f"   Falling back to normal processing...")
                resume = False  # Fall back to normal mode
                tmp_dir = tempfile.mkdtemp()
            else:
                print(f"📂 Resuming from existing directory: {tmp_dir}")

        if not resume and interactive:
            # Use persistent directory in interactive mode
            tmp_dir = f"/tmp/gerrit-pr-{repo}-{change_id}"
            # Clean up if exists
            if os.path.exists(tmp_dir):
                print(f"🧹 Cleaning up existing directory: {tmp_dir}")
                import shutil
                shutil.rmtree(tmp_dir)
            os.makedirs(tmp_dir, exist_ok=True)
            print(f"📁 Working directory: {tmp_dir}")
        else:
            tmp_dir = tempfile.mkdtemp()

        try:
            if resume:
                # Skip clone and patch application in resume mode
                print("⏩ Skipping clone and patch application (resume mode)")
            else:
                # Clone upstream repository
                repo_url = f'https://github.com/sonic-net/{repo}.git'
                self.run_command(['git', 'clone', '--depth=1', repo_url, tmp_dir])
            
            if not resume:
                # Add fork as remote
                fork_url = f'https://github.com/{self.fork_org}/{repo}.git'
                self.run_command(['git', 'remote', 'add', 'fork', fork_url], cwd=tmp_dir)

                # Create feature branch based on target branch (not always master)
                feature_branch_name = f'gerrit-{change_id}-{repo}-{target_branch}'

                # Try to use the target branch if it exists, fallback to master
                try:
                    self.run_command(['git', 'checkout', '-B', feature_branch_name, f'origin/{target_branch}'], cwd=tmp_dir)
                    print(f"Using target branch: {target_branch}")
                except subprocess.CalledProcessError:
                    print(f"Target branch {target_branch} not found, using master")
                    self.run_command(['git', 'checkout', '-B', feature_branch_name, f'origin/master'], cwd=tmp_dir)
                    target_branch = 'master'  # Update for PR creation

                # Apply patches
                for patch_name, patch_content in patches:
                    patch_path = Path(tmp_dir) / patch_name
                    patch_path.write_text(patch_content)

                    try:
                        # Try git am first (preserves commit message)
                        self.run_command(['git', 'am', '-3', str(patch_path)], cwd=tmp_dir)
                        print(f"✅ Applied {patch_name} with git am")
                    except subprocess.CalledProcessError:
                        print(f"⚠️ git am failed for {patch_name}, trying git apply...")
                        try:
                            # Abort the failed am
                            self.run_command(['git', 'am', '--abort'], cwd=tmp_dir)
                        except:
                            pass

                        try:
                            # Fallback: use git apply (loses commit message but applies changes)
                            self.run_command(['git', 'apply', str(patch_path)], cwd=tmp_dir)

                            # Extract commit info from patch
                            subject = self.extract_subject_from_patch(patch_content)
                            description = self.extract_description_from_patch(patch_content)
                            commit_msg = f"{subject}\n\n{description}"

                            # Create commit manually
                            self.run_command(['git', 'add', '-A'], cwd=tmp_dir)
                            self.run_command(['git', 'commit', '-m', commit_msg], cwd=tmp_dir)
                            print(f"✅ Applied {patch_name} with git apply + manual commit")
                        except subprocess.CalledProcessError as e:
                            print(f"❌ Failed to apply {patch_name} even with git apply")
                            print(f"   Error: {e}")

                            # Try AI-powered resolution
                            if self.use_ai_resolution:
                                print(f"🤖 Trying AI-powered patch resolution...")
                                if self.ai_resolve_patch(patch_content, str(patch_path), tmp_dir):
                                    # Extract commit info from patch
                                    subject = self.extract_subject_from_patch(patch_content)
                                    description = self.extract_description_from_patch(patch_content)
                                    commit_msg = f"{subject}\n\n{description}\n\n(Applied with AI assistance)"

                                    # Create commit manually
                                    self.run_command(['git', 'add', '-A'], cwd=tmp_dir)
                                    self.run_command(['git', 'commit', '-m', commit_msg], cwd=tmp_dir)
                                    print(f"✅ Applied {patch_name} with AI resolution")
                                    continue
                                else:
                                    print(f"❌ AI resolution also failed")

                            if interactive:
                                print(f"\n{'='*80}")
                                print(f"🛠️  MANUAL CONFLICT RESOLUTION REQUIRED")
                                print(f"{'='*80}")
                                print(f"Working directory: {tmp_dir}")
                                print(f"Patch file: {patch_path}")
                                print(f"\nTo fix manually:")
                                print(f"1. cd {tmp_dir}")
                                print(f"2. Fix conflicts manually or apply patch with adjustments")
                                print(f"3. git add -A")
                                print(f"4. git commit -m 'Your commit message'")
                                print(f"5. Run this script again with --resume to continue")
                                print(f"{'='*80}\n")
                                raise SystemExit(1)
                            else:
                                raise
            
            # Smart push logic: check if branch exists and handle incrementally
            branch_exists = self.check_branch_exists_in_fork(repo, feature_branch_name)

            if branch_exists and not resume:
                print(f"🔍 Branch {feature_branch_name} already exists in fork")
                print(f"   Fetching existing branch to preserve history...")

                # Fetch the existing branch
                self.run_command(['git', 'fetch', 'fork', feature_branch_name], cwd=tmp_dir)

                # Get the commit hash of our new changes
                result = self.run_command(['git', 'rev-parse', 'HEAD'], cwd=tmp_dir, capture_output=True)
                new_commit = result.stdout.strip()

                # Get the commit hash of the existing branch
                result = self.run_command(['git', 'rev-parse', 'fork/' + feature_branch_name], cwd=tmp_dir, capture_output=True)
                old_commit = result.stdout.strip()

                if new_commit == old_commit:
                    print(f"✅ Branch is already up to date (commit: {new_commit[:8]})")
                    branch_url = f"https://github.com/{self.fork_org}/{repo}/tree/{feature_branch_name}"
                    print(f"   Branch URL: {branch_url}")
                    return None

                print(f"   Old commit: {old_commit[:8]}")
                print(f"   New commit: {new_commit[:8]}")
                print(f"   Creating incremental update...")

                # Check out the existing branch
                self.run_command(['git', 'checkout', '-B', feature_branch_name, 'fork/' + feature_branch_name], cwd=tmp_dir)

                # Cherry-pick the new changes
                try:
                    # Get list of commits from upstream base to new HEAD
                    # We need to cherry-pick only the new patch commits
                    result = self.run_command(['git', 'rev-list', '--reverse', f'fork/{feature_branch_name}..{new_commit}'],
                                             cwd=tmp_dir, capture_output=True)
                    commits_to_cherry_pick = result.stdout.strip().split('\n')
                    commits_to_cherry_pick = [c for c in commits_to_cherry_pick if c]  # Filter empty

                    if commits_to_cherry_pick:
                        print(f"   Cherry-picking {len(commits_to_cherry_pick)} new commit(s)...")
                        for commit in commits_to_cherry_pick:
                            self.run_command(['git', 'cherry-pick', commit], cwd=tmp_dir)
                        print(f"✅ Successfully applied incremental changes")
                    else:
                        print(f"   No new commits to cherry-pick")

                except subprocess.CalledProcessError as e:
                    print(f"⚠️ Cherry-pick failed, may have conflicts")
                    print(f"\n{'='*80}")
                    print(f"🛠️  CHERRY-PICK CONFLICT - MANUAL RESOLUTION REQUIRED")
                    print(f"{'='*80}")
                    print(f"Working directory: {tmp_dir}")
                    print(f"\nTo fix manually:")
                    print(f"1. cd {tmp_dir}")
                    print(f"2. Resolve conflicts")
                    print(f"3. git add -A && git cherry-pick --continue")
                    print(f"4. Run this script again with --resume")
                    print(f"{'='*80}\n")
                    print(f"⚠️ IMPORTANT: Force push has been disabled for safety.")
                    print(f"   Please resolve conflicts manually and use --resume to continue.")
                    raise SystemExit(1)

            # Push to fork - ALWAYS use regular push (never force push, even for first time)
            # This ensures all changes are incremental commits and history is never overwritten
            try:
                self.run_command(['git', 'push', 'fork', feature_branch_name], cwd=tmp_dir)
            except subprocess.CalledProcessError as e:
                # If push fails due to branch not existing, set upstream and push
                print(f"Branch doesn't exist in fork yet, creating it...")
                self.run_command(['git', 'push', '-u', 'fork', feature_branch_name], cwd=tmp_dir)

            branch_url = f"https://github.com/{self.fork_org}/{repo}/tree/{feature_branch_name}"
            print(f"✅ Pushed branch: {feature_branch_name}")
            print(f"   Branch URL: {branch_url}")
            print(f"   Target: sonic-net/{repo} (base: {target_branch})")
            return None  # Return None since we're not creating PRs
        finally:
            # Clean up temp directory only if not in interactive mode
            if not interactive and tmp_dir and os.path.exists(tmp_dir):
                import shutil
                shutil.rmtree(tmp_dir)
    
    def post_gerrit_comment(self, change_id: str, pr_urls: List[str]):
        """Post comment to Gerrit with PR links for internal team notification"""
        try:
            pr_links = "\n".join(f"- {url}" for url in pr_urls)
            
            comment_message = f"""🚀 **Upstream PRs Created (Internal Review)**

**GitHub Pull Requests:**
{pr_links}

**📋 Next Steps:**
1. Internal team: Review PRs above (private forks)
2. Address any feedback and update patches
3. When ready: Comment "Make-Public" to transfer to public upstream repos
4. Monitor upstream community review process

**⚠️ Note:** These PRs are currently in private forks for internal review. They will be made public and submitted to sonic-net repositories once approved internally.

*Generated automatically from Gerrit change {change_id}*"""

            # Post comment to Gerrit
            url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/current/review"
            data = {"message": comment_message}
            
            response = requests.post(url, 
                                   auth=(self.username, self.password),
                                   json=data,
                                   headers={'Content-Type': 'application/json'})
            
            if response.status_code == 200:
                print(f"✅ Posted Gerrit comment with PR links for internal team")
            else:
                print(f"⚠️ Failed to post Gerrit comment: {response.status_code}")
                
        except Exception as e:
            print(f"⚠️ Failed to post Gerrit comment: {e}")


def main():
    parser = argparse.ArgumentParser(description='Convert Gerrit change to GitHub PRs')
    parser.add_argument('--change', required=True, help='Gerrit change ID')
    parser.add_argument('--token', required=True, help='GitHub personal access token')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without executing')
    parser.add_argument('--interactive', action='store_true', help='Keep working directory for manual conflict resolution')
    parser.add_argument('--ai-resolve', action='store_true', help='Use AI to resolve patch conflicts automatically')
    parser.add_argument('--resume', action='store_true', help='Resume from existing working directory (skip clone and patch application)')
    parser.add_argument('--gcp-project', help='GCP project for AI resolution (requires --ai-resolve)')
    parser.add_argument('--gerrit-url', default=os.getenv('GERRIT_URL', 'https://gerrit.corp.arista.io'))
    parser.add_argument('--gerrit-user', default=os.getenv('GERRIT_USERNAME', ''))
    parser.add_argument('--gerrit-pass', default=os.getenv('GERRIT_PASSWORD', ''))
    parser.add_argument('--config', help='Use existing gerrit_config.json file')

    args = parser.parse_args()
    
    # Load credentials from config file if provided
    gerrit_user = args.gerrit_user
    gerrit_pass = args.gerrit_pass
    gerrit_url = args.gerrit_url
    
    if args.config and os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = json.load(f)
        gerrit_user = gerrit_user or config.get('username', '')
        gerrit_pass = gerrit_pass or config.get('password', '')
        gerrit_url = config.get('gerrit_url', gerrit_url)
        print(f"DEBUG: Loaded config - URL: {gerrit_url}, User: {gerrit_user}, Pass length: {len(gerrit_pass) if gerrit_pass else 0}", file=sys.stderr)
    
    if not gerrit_user or not gerrit_pass:
        print("Error: Gerrit credentials required. Set GERRIT_USERNAME and GERRIT_PASSWORD, use --gerrit-user/--gerrit-pass, or provide --config file")
        return 1
    
    try:
        converter = GerritToPRConverter(
            gerrit_url,
            gerrit_user,
            gerrit_pass,
            args.token,
            use_ai_resolution=args.ai_resolve,
            gcp_project=args.gcp_project or os.getenv('GOOGLE_CLOUD_PROJECT')
        )
        
        results = converter.process_change(args.change, dry_run=args.dry_run, interactive=args.interactive, resume=args.resume)

        # Count successful branch pushes (filter out None values)
        branch_count = sum(1 for _ in results)

        print(f"\n✅ Successfully pushed {branch_count} branches to fork")
        print(f"   You can now create PRs manually from your fork on GitHub")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
