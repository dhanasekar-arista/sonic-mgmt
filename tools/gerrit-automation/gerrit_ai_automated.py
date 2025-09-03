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
    def __init__(self, provider: str = "oracle", api_key: str = None):
        self.provider = provider
        self.api_key = api_key
    
    def analyze_patches(self, patch_paths: list, subject: str) -> tuple:
        """Analyze patches and return (analysis_text, score)"""
        
        if self.provider == "oracle":
            return self._oracle_analysis(patch_paths, subject)
        elif self.provider == "gemini" and self.api_key:
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
        """Use Gemini AI for analysis"""
        print("🤖 Calling Gemini AI...")
        
        # Combine all patch content
        combined_patches = ""
        for path in patch_paths:
            with open(path, 'r') as f:
                combined_patches += f"\\n--- {os.path.basename(path)} ---\\n{f.read()}\\n"
        
        prompt = f"""Analyze these SONiC patches from change '{subject}':

{combined_patches[:4000]}

Provide:
1. Functional analysis of each patch
2. Technical impact on SONiC
3. Final recommendation: +1 (approve), 0 (neutral), or -1 (reject)

End your response with 'SCORE: +1' or 'SCORE: -1' or 'SCORE: 0'"""

        try:
            # Call Gemini API (Google AI Studio API)
            headers = {
                'Content-Type': 'application/json'
            }
            
            # Gemini API endpoint
            url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.api_key}'
            
            data = {
                'contents': [{
                    'parts': [{'text': prompt}]
                }],
                'generationConfig': {
                    'maxOutputTokens': 500,
                    'temperature': 0.2
                }
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result_json = response.json()
                if 'candidates' in result_json and len(result_json['candidates']) > 0:
                    result_text = result_json['candidates'][0]['content']['parts'][0]['text']
                    
                    # Extract score
                    score = 0
                    if any(word in result_text.lower() for word in ['+1', 'approve', 'looks good']):
                        score = 1
                    elif any(word in result_text.lower() for word in ['-1', 'reject', 'critical', 'breaks']):
                        score = -1
                    
                    return result_text, score
                else:
                    return "Gemini API: No response content", 0
            else:
                return f"Gemini API error: {response.status_code}", 0
                
        except Exception as e:
            return f"Gemini analysis failed: {str(e)}", 0

def create_draft_prs(change_id: str, github_token: str, config_file: str) -> list:
    """Create draft PRs"""
    if not github_token or '[REDACTED:' in github_token:
        return []
    
    try:
        cmd = ['python3', 'gerrit_to_pr.py', '--change', change_id, 
               '--token', github_token, '--config', config_file]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        pr_urls = []
        for line in result.stdout.split('\\n'):
            if 'https://github.com/' in line and '/pull/' in line:
                pr_urls.append(line.strip())
        
        return pr_urls
        
    except subprocess.CalledProcessError:
        return []

def main():
    parser = argparse.ArgumentParser(description='Automated Generic AI Gerrit Review')
    parser.add_argument('--change-id', required=True, help='Gerrit change ID')
    parser.add_argument('--config', default='gerrit_config.json', help='Config file')
    parser.add_argument('--ai-provider', choices=['oracle', 'gemini'], default='oracle', help='AI provider')
    parser.add_argument('--api-key', help='API key for AI provider (required for Gemini)')
    parser.add_argument('--submit', action='store_true', help='Submit review')
    parser.add_argument('--create-prs', action='store_true', help='Create PRs')
    parser.add_argument('--github-token', help='GitHub token for PR creation')
    
    args = parser.parse_args()
    
    # Validate AI provider setup
    if args.ai_provider == 'gemini' and not args.api_key:
        print("❌ Error: --api-key required when using Gemini")
        sys.exit(1)
    
    # Load config
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    gerrit_client = GerritClient(config['gerrit_url'], config['username'], config['password'])
    ai_analyzer = AIAnalyzer(args.ai_provider, args.api_key)
    
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
            print("🔧 Creating draft PRs...")
            github_token = args.github_token or config.get('github_token')
            pr_urls = create_draft_prs(args.change_id, github_token, args.config)
            if pr_urls:
                pr_status = f"\\n\\n**🚀 Draft PRs Created:**\\n" + "\\n".join(f"- {url}" for url in pr_urls)
            else:
                pr_status = "\\n\\n**❌ Draft PRs:** Creation failed or no GitHub token"
        
        # Submit to Gerrit if requested
        if args.submit:
            print("🚀 Submitting AI review to Gerrit...")
            
            final_message = f"🤖 **{args.ai_provider.upper()} AI-Powered SONiC Review**\\n\\n{ai_analysis}{pr_status}"
            
            success = gerrit_client.submit_review(args.change_id, revision_id, final_message, ai_score)
            if success:
                print(f"✅ Review submitted with score {ai_score}")
            else:
                print("❌ Failed to submit review")
        else:
            print("📋 Analysis complete - use --submit to post review")
            print(f"📊 Analysis: {ai_analysis}")
    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
