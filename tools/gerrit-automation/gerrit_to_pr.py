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
    
    def __init__(self, gerrit_url: str, username: str, password: str, github_token: str):
        self.gerrit_url = gerrit_url.rstrip('/')
        self.username = username
        self.password = password
        self.github_token = github_token
        
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
    
    def create_github_pr(self, repo: str, target_branch: str, feature_branch: str, patches: List[Tuple[str, str]], change_id: str) -> str:
        """Create or update GitHub PR"""
        
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
        
        # Check if PR already exists
        github_api_url = f"https://api.github.com/repos/sonic-net/{repo}/pulls"
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github+json'
        }
        
        # Look for existing PR
        params = {'head': f'{self.fork_org}:{feature_branch}', 'base': target_branch}
        existing_prs = requests.get(github_api_url, headers=headers, params=params)
        
        if existing_prs.status_code == 200 and existing_prs.json():
            # Update existing PR
            pr_number = existing_prs.json()[0]['number']
            update_url = f"https://api.github.com/repos/sonic-net/{repo}/pulls/{pr_number}"
            requests.patch(update_url, headers=headers, json={'title': title, 'body': body})
            return f"https://github.com/sonic-net/{repo}/pull/{pr_number}"
        else:
            # Create new PR as draft for internal review
            pr_data = {
                'title': f"[DRAFT] {title}",
                'head': f'{self.fork_org}:{feature_branch}',
                'base': target_branch,
                'body': f"🚧 **DRAFT - Internal Review** 🚧\n\n{body}\n\n---\n⚠️ This PR is in draft mode for internal Arista review. Will be marked ready when approved internally.",
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
    
    def process_change(self, change_id: str, dry_run: bool = False) -> List[str]:
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
            pr_url = self.create_pr_for_repo(repo, branch, patches, change_id)
            pr_urls.append(pr_url)
        
        return pr_urls
    
    def create_pr_for_repo(self, repo: str, target_branch: str, patches: List[Tuple[str, str]], change_id: str) -> str:
        """Create GitHub PR for a specific repository and branch"""
        print(f"\nCreating PR for {repo} (target branch: {target_branch}) with {len(patches)} patches...")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Clone upstream repository
            repo_url = f'https://github.com/sonic-net/{repo}.git'
            self.run_command(['git', 'clone', '--depth=1', repo_url, tmp_dir])
            
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
                    # Apply patch with 3-way merge
                    self.run_command(['git', 'am', '-3', str(patch_path)], cwd=tmp_dir)
                    print(f"Applied {patch_name} successfully")
                except subprocess.CalledProcessError:
                    print(f"Failed to apply {patch_name} - may need manual resolution")
                    raise
            
            # Push to fork
            self.run_command(['git', 'push', '-f', 'fork', feature_branch_name], cwd=tmp_dir)
            
            # Create GitHub PR
            pr_url = self.create_github_pr(repo, target_branch, feature_branch_name, patches, change_id)
            print(f"Created/updated PR: {pr_url}")
            
            return pr_url
    
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
            args.token
        )
        
        pr_urls = converter.process_change(args.change, dry_run=args.dry_run)
        
        # Write PR URLs to temp file for gerrit_ai_automated.py to read
        temp_file = f"/tmp/pr_urls_{args.change}.json"
        with open(temp_file, 'w') as f:
            json.dump({"pr_urls": pr_urls, "change_id": args.change}, f)
        
        print(f"✅ Successfully processed {len(pr_urls)} PRs")
        for url in pr_urls:
            print(f"  - {url}")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
