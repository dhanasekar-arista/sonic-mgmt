#!/usr/bin/env python3
"""
Automated Generic SONiC Gerrit AI Review Tool

Supports:
- Oracle AI (built-in)  
- Gemini AI (with API key)
- Automatic patch extraction
- AI-based scoring
- Draft PR creation
- Gerrit comment posting
"""

import os
import sys
import json
import requests
import argparse
import base64
import tempfile
import subprocess
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel, Part

class GerritClient:
    def __init__(self, gerrit_url: str, username: str, password: str):
        self.gerrit_url = gerrit_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.auth = (username, password)
    
    def get_change_details(self, change_id: str) -> dict:
        url = f"{self.gerrit_url}/a/changes/{change_id}/detail"
        response = self.session.get(url)
        response.raise_for_status()
        response_text = response.text
        if response_text.startswith(")]}'\n"):
            response_text = response_text[5:]
        return json.loads(response_text)
    
    def get_change_files(self, change_id: str, revision_id: str) -> dict:
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/files"
        response = self.session.get(url)
        response.raise_for_status()
        response_text = response.text
        if response_text.startswith(")]}'\n"):
            response_text = response_text[5:]
        return json.loads(response_text)
    
    def get_file_content(self, change_id: str, revision_id: str, file_path: str) -> str:
        import urllib.parse
        encoded_file_path = urllib.parse.quote(file_path, safe='')
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/files/{encoded_file_path}/content"
        
        response = self.session.get(url)
        response.raise_for_status()
        response_text = response.text
        if response_text.startswith(")]}'\n"):
            response_text = response_text[5:]
        
        if response_text.startswith('"') and response_text.endswith('"'):
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                pass
        
        try:
            missing_padding = len(response_text) % 4
            if missing_padding:
                response_text += '=' * (4 - missing_padding)
            return base64.b64decode(response_text).decode('utf-8')
        except:
            return response_text
    
    def submit_review(self, change_id: str, revision_id: str, message: str, score: int) -> bool:
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/review"
        review_data = {
            "message": message,
            "labels": {"Code-Review": score}
        }
        response = self.session.post(url, json=review_data)
        return response.status_code == 200

class AIAnalyzer:
    def __init__(self, provider: str = "oracle", api_key: str = None,
                 gcp_project: str = None, gcp_location: str = "us-east5"):
        self.provider = provider
        self.api_key = api_key
        self.gcp_project = gcp_project
        self.gcp_location = gcp_location
    
    def analyze_patches(self, patch_paths: list, subject: str) -> tuple:
        """Analyze patches and return (analysis_text, score)"""

        if self.provider == "oracle":
            return self._oracle_analysis(patch_paths, subject)
        elif self.provider == "gemini":
            return self._gemini_analysis(patch_paths, subject)
        else:
            return f"**📋 Change:** {subject}\\n**❌ Error:** AI provider '{self.provider}' not available", 0
    
    def _oracle_analysis(self, patch_paths: list, subject: str) -> tuple:
        """Use Oracle AI for analysis"""
        print("🔮 Calling Oracle AI...")
        
        # Create the Oracle analysis command
        oracle_prompt = f"""Analyze these SONiC patches from Gerrit change '{subject}':

1. Provide functional analysis of changes in each patch
2. Assess technical impact on SONiC system  
3. Recommend approval score: +1 (approve), 0 (neutral), or -1 (reject) with justification

Be concise and specific. Format as a Gerrit review comment."""
        
        # For Oracle analysis, integrate the analysis we obtained from the Oracle tool
        oracle_response = self._get_oracle_response(patch_paths, subject)
        
        # Extract score from Oracle response
        score = 0  # Default neutral
        if any(word in oracle_response.lower() for word in ['approve', 'looks good', 'acceptable', 'approved']):
            score = 1
        elif any(word in oracle_response.lower() for word in ['reject', 'critical', 'breaks', 'fails', 'do not submit']):
            score = -1
        
        analysis = f"**🔮 Oracle AI Analysis:**\\n\\n{oracle_response}"
        return analysis, score
    
    def _get_oracle_response(self, patch_paths: list, subject: str) -> str:
        """Get Oracle AI response using amp CLI"""
        print("📡 Calling Oracle through amp CLI...")
        
        try:
            # Create Oracle prompt with file attachment
            oracle_prompt = f"Use oracle to analyze these SONiC patches from Gerrit change '{subject}'. Files: {', '.join(patch_paths)}. Provide: 1) Functional analysis of each patch 2) Technical impact on SONiC 3) Recommendation +1 (approve), 0 (neutral), or -1 (reject) with justification. Be concise and specific."
            
            # Call amp CLI with Oracle
            result = subprocess.run(
                ['amp', '-x'],
                input=oracle_prompt,
                text=True,
                capture_output=True,
                timeout=120
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            else:
                print(f"Amp CLI stderr: {result.stderr}")
                return f"Oracle analysis failed - amp CLI error"
                
        except Exception as e:
            print(f"Oracle call failed: {e}")
            return f"Oracle unavailable: {str(e)}"
    
    def _gemini_analysis(self, patch_paths: list, subject: str) -> tuple:
        """Use Gemini AI via Vertex AI for analysis"""
        print("🤖 Calling Gemini AI via Vertex AI...")

        # Validate Vertex AI prerequisites
        if not self.gcp_project:
            return "Gemini via Vertex AI: GCP project not specified", 0

        # Combine all patch content with smart truncation
        # Allocate tokens fairly across patches
        max_total_chars = 12000  # Total chars for all patches
        chars_per_patch = max_total_chars // max(len(patch_paths), 1)

        combined_patches = ""
        for path in patch_paths:
            with open(path, 'r') as f:
                patch_content = f.read()
                # Truncate each patch fairly
                if len(patch_content) > chars_per_patch:
                    combined_patches += f"\\n--- {os.path.basename(path)} (truncated: {len(patch_content)} chars total) ---\\n{patch_content[:chars_per_patch]}\\n"
                else:
                    combined_patches += f"\\n--- {os.path.basename(path)} ---\\n{patch_content}\\n"

        prompt = f"""Analyze SONiC Gerrit change '{subject}' with {len(patch_paths)} patches:

{combined_patches}

Review:
1. Functional: What features are added/modified?
2. Impact: Effects on SONiC components (swss, sairedis, utilities)?
3. Issues: Any bugs, compilation errors, or problems?
4. Score:
   +1 = Good, ready to merge
   0 = Minor issues/needs review (default)
   -1 = ONLY for definite compilation errors or critical bugs

End with 'SCORE: +1', 'SCORE: 0', or 'SCORE: -1'"""

        # Try multiple Gemini models via Vertex AI
        models = ['gemini-2.5-flash', 'gemini-2.0-flash-exp', 'gemini-1.5-flash-002']

        for model in models:
            try:
                print(f"🤖 Trying Vertex AI Gemini model: {model}")

                # Initialize Vertex AI
                aiplatform.init(project=self.gcp_project, location=self.gcp_location)

                # Create generative model
                generative_model = GenerativeModel(model)

                # Generate content
                response = generative_model.generate_content(
                    prompt,
                    generation_config={
                        'max_output_tokens': 4096,
                        'temperature': 0.3,
                    }
                )

                # Extract result text
                if response and response.text:
                    result_text = response.text

                    print(f"✅ Successfully got response from {model}")

                    # Extract score
                    score = 0
                    if any(word in result_text.lower() for word in ['+1', 'approve', 'looks good']):
                        score = 1
                    elif any(word in result_text.lower() for word in ['-1', 'reject', 'critical', 'breaks']):
                        score = -1

                    return result_text, score
                else:
                    print(f"❌ Model {model}: No response content")
                    if response:
                        print(f"📊 Response object: {response}")
                    continue

            except Exception as e:
                print(f"❌ Model {model} exception: {e}")
                import traceback
                traceback.print_exc()
                continue

        # All models failed
        return "Gemini via Vertex AI: All models failed", 0

def check_existing_prs(change_id: str, github_token: str) -> list:
    """Check for existing PRs for this Gerrit change"""
    if not github_token or '[REDACTED:' in github_token:
        print("❌ No GitHub token for PR search")
        return []
    
    print(f"🔍 Searching for existing PRs with change ID {change_id}...")
    
    try:
        headers = {'Authorization': f'token {github_token}'}
        
        # Check common SONiC repos for existing PRs
        repos = ['sonic-net/sonic-buildimage', 'sonic-net/sonic-utilities', 'sonic-net/sonic-mgmt']
        existing_prs = []
        
        for repo in repos:
            # Search for PRs containing the change ID
            url = f'https://api.github.com/search/issues?q=repo:{repo}+type:pr+{change_id}+in:title,body+state:open'
            print(f"🔍 Searching {repo}...")
            
            response = requests.get(url, headers=headers, timeout=10)
            print(f"   Response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                count = data.get('total_count', 0)
                print(f"   Found: {count} PRs")
                
                for item in data.get('items', []):
                    pr_url = item['html_url']
                    existing_prs.append(pr_url)
                    print(f"   PR: {pr_url}")
            else:
                print(f"   Search failed: {response.status_code}")
        
        if existing_prs:
            print(f"✅ Found {len(existing_prs)} total existing PR(s)")
        else:
            print("❌ No existing PRs found")
        
        return existing_prs
        
    except Exception as e:
        print(f"❌ PR search failed: {e}")
        return []

def create_draft_prs(change_id: str, github_token: str, config_file: str) -> list:
    """Create draft PRs or return existing PR links"""
    if not github_token:
        print("❌ No GitHub token provided")
        return []
    
    if '[REDACTED:' in github_token:
        print("❌ GitHub token is redacted - cannot create PRs")
        return []
    
    print(f"🔧 GitHub token available: {github_token[:10]}...{github_token[-4:]}")
    print(f"🔧 Config file: {config_file}")
    print(f"🔧 Change ID: {change_id}")
    
    # Always try to create PRs - gerrit_to_pr.py will handle per-repo logic
    try:
        # Check if gerrit_to_pr.py exists
        if not os.path.exists('gerrit_to_pr.py'):
            print("❌ gerrit_to_pr.py not found in current directory")
            return []
        
        print("🔧 Calling gerrit_to_pr.py...")
        cmd = ['python3', 'gerrit_to_pr.py', '--change', change_id,
               '--token', github_token, '--config', config_file,
               '--ai-resolve', '--gcp-project', os.getenv('GOOGLE_CLOUD_PROJECT', '')]
        print(f"🔧 Command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Read PR URLs from temp file instead of parsing stdout
        temp_file = f"/tmp/pr_urls_{change_id}.json"
        pr_urls = []
        
        try:
            if os.path.exists(temp_file):
                with open(temp_file, 'r') as f:
                    data = json.load(f)
                    pr_urls = data.get('pr_urls', [])
                
                # Clean up temp file
                os.remove(temp_file)
                
                if pr_urls:
                    print(f"✅ Read {len(pr_urls)} PR URLs from temp file")
                    return pr_urls
        
        except Exception as e:
            print(f"❌ Failed to read PR URLs from temp file: {e}")
        
        # Fallback: check for errors in subprocess output
        if result.returncode != 0:
            print(f"❌ PR Creation Error:")
            print(f"   Return code: {result.returncode}")
            if "401" in result.stdout or "Unauthorized" in result.stdout:
                print("🔑 GitHub Authentication Error - Invalid token")
            elif "404" in result.stdout:
                print("🔍 Repository not found")
        
        return []
        
    except subprocess.CalledProcessError as e:
        print(f"❌ PR Creation Error:")
        print(f"   Return code: {e.returncode}")
        print(f"   Stdout: {e.stdout}")
        print(f"   Stderr: {e.stderr}")
        
        # Check specific error types
        if "401" in str(e.stdout) or "Unauthorized" in str(e.stdout):
            print("🔑 GitHub Authentication Error - Invalid token or insufficient permissions")
            return []
        elif "already exists" in str(e.stdout) or "branch exists" in str(e.stderr):
            print("🔍 Checking for existing PRs due to branch conflict...")
            existing_prs = check_existing_prs(change_id, github_token)
            if existing_prs:
                return existing_prs
        elif "404" in str(e.stdout) or "Not Found" in str(e.stdout):
            print("🔍 Repository not found or not accessible")
            return []
        
        return []

def main():
    parser = argparse.ArgumentParser(description='Automated Generic AI Gerrit Review')
    parser.add_argument('--change-id', required=True, help='Gerrit change ID')
    parser.add_argument('--config', default='gerrit_config.json', help='Config file')
    parser.add_argument('--ai-provider', choices=['oracle', 'gemini'], default='oracle', help='AI provider')
    parser.add_argument('--api-key', help='API key for AI provider (not used with Vertex AI)')
    parser.add_argument('--gcp-project', help='GCP project ID for Vertex AI (required for Gemini)')
    parser.add_argument('--gcp-location', default='us-east5', help='GCP location for Vertex AI (default: us-east5)')
    parser.add_argument('--submit', action='store_true', help='Submit review')
    parser.add_argument('--create-prs', action='store_true', help='Create PRs')
    parser.add_argument('--github-token', help='GitHub token for PR creation')

    args = parser.parse_args()

    # Validate AI provider setup
    if args.ai_provider == 'gemini' and not args.gcp_project:
        print("❌ Error: --gcp-project required when using Gemini via Vertex AI")
        sys.exit(1)
    
    # Load config
    with open(args.config, 'r') as f:
        config = json.load(f)

    gerrit_client = GerritClient(config['gerrit_url'], config['username'], config['password'])
    ai_analyzer = AIAnalyzer(
        provider=args.ai_provider,
        api_key=args.api_key,
        gcp_project=args.gcp_project,
        gcp_location=args.gcp_location
    )

    print(f"🤖 Analyzing change {args.change_id} with {args.ai_provider.upper()} AI...")
    
    try:
        # Extract patches
        change_details = gerrit_client.get_change_details(args.change_id)
        revision_id = str(change_details.get('current_revision_number', 'current'))
        subject = change_details.get('subject', '')
        
        files_info = gerrit_client.get_change_files(args.change_id, revision_id)
        
        # Download patches
        patch_files = {}
        for file_path in files_info.keys():
            if file_path.endswith('.patch'):
                try:
                    content = gerrit_client.get_file_content(args.change_id, revision_id, file_path)
                    patch_files[file_path] = content
                    print(f"✅ Retrieved: {file_path}")
                except Exception as e:
                    print(f"❌ Failed to get {file_path}: {e}")
        
        if not patch_files:
            print("❌ No patch files found")
            return
        
        # Save patches for AI analysis
        patch_paths = []
        for i, (file_path, content) in enumerate(patch_files.items()):
            patch_name = file_path.split('/')[-1]
            temp_path = f"/tmp/patch_{args.change_id}_{i}_{patch_name}"
            with open(temp_path, 'w') as f:
                f.write(content)
            patch_paths.append(temp_path)
            print(f"📝 Saved: {temp_path}")
        
        # AI Analysis
        ai_analysis, ai_score = ai_analyzer.analyze_patches(patch_paths, subject)
        
        print(f"📊 AI Analysis Complete: Score {ai_score}")
        
        # Create PRs if requested
        pr_status = ""
        if args.create_prs:
            print("🔧 Processing draft PRs...")
            github_token = args.github_token or config.get('github_token')
            
            # Check for existing PRs first
            existing_prs = check_existing_prs(args.change_id, github_token)
            
            # Try to create new PRs (gerrit_to_pr.py handles per-repo logic)
            new_pr_urls = create_draft_prs(args.change_id, github_token, args.config)
            
            # Combine existing and newly created PRs
            all_pr_urls = list(set(existing_prs + new_pr_urls))  # Remove duplicates
            
            if all_pr_urls:
                # Clean PR status for Gerrit comment (no debug details)
                pr_status = f"\\n\\n**🚀 Draft PRs:**\\n" + "\\n".join(f"- {url}" for url in all_pr_urls)
                
                # Console output with details (not in Gerrit comment)
                if existing_prs and new_pr_urls:
                    print(f"📊 PR Summary: {len(existing_prs)} existing + {len(new_pr_urls)} newly created = {len(all_pr_urls)} total")
                elif existing_prs:
                    print(f"📊 PR Summary: {len(existing_prs)} existing PRs found")
                else:
                    print(f"📊 PR Summary: {len(new_pr_urls)} new PRs created")
            else:
                pr_status = "\\n\\n**❌ Draft PRs:** Creation failed"
        
        # Submit to Gerrit if requested
        if args.submit:
            print("🚀 Submitting AI review to Gerrit...")
            
            # Clean up AI analysis for Gerrit (remove debug formatting)
            clean_analysis = ai_analysis.replace("\\n\\n", "\\n").replace("**🔮 Oracle AI Analysis:**\\n\\n", "")
            
            final_message = f"🤖 **{args.ai_provider.upper()} AI Review**\\n\\n{clean_analysis}{pr_status}"
            
            success = gerrit_client.submit_review(args.change_id, revision_id, final_message, ai_score)
            if success:
                print(f"✅ Review submitted with score {ai_score}")
            else:
                print("❌ Failed to submit review")
        else:
            print("\n" + "="*80)
            print("📋 ANALYSIS COMPLETE - Use --submit to post review to Gerrit")
            print("="*80)
            print("\n📊 AI ANALYSIS:\n")
            print(ai_analysis)
            print("\n" + "="*80)
    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
