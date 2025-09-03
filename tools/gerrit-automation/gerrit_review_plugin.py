#!/usr/bin/env python3
"""
Gerrit Code Review Plugin - Automated Code Review Tool

Features:
- Automated code review using AI analysis
- SONiC-specific patch validation
- Gerrit API integration for submitting reviews
- Configurable review criteria
"""

import os
import sys
import json
import requests
import argparse
import subprocess
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

# Enhanced diff analysis dependencies
try:
    from unidiff import PatchSet
    UNIDIFF_AVAILABLE = True
except ImportError:
    UNIDIFF_AVAILABLE = False
    print("Warning: unidiff not available. Install with: pip install unidiff")

try:
    from rich.console import Console
    from rich.syntax import Syntax
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: rich not available. Install with: pip install rich")


@dataclass
class ReviewComment:
    file_path: str
    line_number: int
    message: str
    severity: str  # 'info', 'warning', 'error'


@dataclass
class DiffStat:
    file_path: str
    lines_added: int
    lines_removed: int
    lines_modified: int
    functions_changed: List[str]

@dataclass
class ReviewResult:
    score: int  # -2, -1, 0, +1, +2
    message: str
    comments: List[ReviewComment]
    diffstats: List[DiffStat] = None


class GerritClient:
    """Gerrit REST API client"""
    
    def __init__(self, gerrit_url: str, username: str, password: str):
        self.gerrit_url = gerrit_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def get_change_details(self, change_id: str) -> Dict:
        """Get change details from Gerrit"""
        url = f"{self.gerrit_url}/a/changes/{change_id}/detail"
        response = self.session.get(url)
        if response.status_code == 200:
            # Remove ")]}'" prefix from Gerrit JSON response
            response_text = response.text
            if response_text.startswith(")]}'\n"):
                response_text = response_text[5:]
            elif response_text.startswith(")]}' "):
                response_text = response_text[5:]
            
            data = json.loads(response_text)
            print(f"DEBUG: Change details keys: {list(data.keys())}")
            return data
        else:
            raise Exception(f"Failed to get change details: {response.status_code} - {response.text}")
    
    def get_change_files(self, change_id: str, revision_id: str = 'current') -> Dict:
        """Get list of files in a change"""
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/files"
        response = self.session.get(url)
        if response.status_code == 200:
            response_text = response.text
            if response_text.startswith(")]}'\n"):
                response_text = response_text[5:]
            elif response_text.startswith(")]}' "):
                response_text = response_text[5:]
            
            files_data = json.loads(response_text)
            print(f"DEBUG: Found {len(files_data)} files: {list(files_data.keys())}")
            return files_data
        else:
            raise Exception(f"Failed to get change files: {response.status_code} - {response.text}")
    
    def get_file_content(self, change_id: str, revision_id: str, file_path: str) -> str:
        """Get file content from a change"""
        # URL encode the file path
        import urllib.parse
        encoded_file_path = urllib.parse.quote(file_path, safe='')
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/files/{encoded_file_path}/content"
        
        print(f"DEBUG: Requesting file content from: {url}")
        response = self.session.get(url)
        if response.status_code == 200:
            import base64
            response_text = response.text
            
            # Remove Gerrit's magic prefix if present
            if response_text.startswith(")]}'\n"):
                response_text = response_text[5:]
            elif response_text.startswith(")]}' "):
                response_text = response_text[5:]
            
            # Check if content is already plain text (not base64)
            if response_text.startswith(('#', 'From:', 'diff', '---', '+++')):
                # Content is already plain text
                return response_text
            
            # Try base64 decoding
            try:
                # Fix base64 padding if needed
                missing_padding = len(response_text) % 4
                if missing_padding:
                    response_text += '=' * (4 - missing_padding)
                
                return base64.b64decode(response_text).decode('utf-8')
            except Exception as e:
                # If base64 fails, assume it's plain text
                print(f"DEBUG: Base64 decode failed, treating as plain text: {e}")
                return response_text
        else:
            print(f"DEBUG: Failed to get {file_path}: {response.status_code} - {response.text[:200]}")
            raise Exception(f"Failed to get file content: {response.status_code}")
    
    def submit_review(self, change_id: str, revision_id: str, review_result: ReviewResult) -> bool:
        """Submit review to Gerrit"""
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/review"
        
        # Prepare review data
        review_data = {
            "message": review_result.message,
            "labels": {
                "Code-Review": review_result.score
            }
        }
        
        # Add inline comments
        if review_result.comments:
            review_data["comments"] = {}
            for comment in review_result.comments:
                if comment.file_path not in review_data["comments"]:
                    review_data["comments"][comment.file_path] = []
                
                review_data["comments"][comment.file_path].append({
                    "line": comment.line_number,
                    "message": f"[{comment.severity.upper()}] {comment.message}"
                })
        
        response = self.session.post(url, json=review_data)
        return response.status_code == 200


class SONiCCodeReviewer:
    """SONiC-specific code review logic"""
    
    def __init__(self):
        self.sonic_patterns = {
            'test_file_patterns': [r'test_.*\.py$', r'.*_test\.py$'],
            'required_imports': ['pytest_assert', 'pytest_require'],
            'forbidden_patterns': [
                r'assert\s+(?!False)',  # Raw assert statements
                r'print\(',  # Print statements in tests
                r'time\.sleep\(\s*[0-9]+\s*\)',  # Hard-coded sleeps
            ],
            'required_markers': ['@pytest.mark.topology']
        }
    
    def _generate_diffstat(self, files: Dict[str, str]) -> List[DiffStat]:
        """Generate diffstat information for patch files"""
        diffstats = []
        
        for file_path, content in files.items():
            if not file_path.endswith('.patch'):
                continue
            
            # Try unidiff parsing first
            patch_set = self._parse_patch_with_unidiff(content)
            if patch_set:
                for patched_file in patch_set:
                    functions_changed = []
                    for hunk in patched_file:
                        if hunk.section_header:
                            func_name = hunk.section_header.strip()
                            if func_name not in functions_changed:
                                functions_changed.append(func_name)
                    
                    diffstat = DiffStat(
                        file_path=patched_file.path,
                        lines_added=patched_file.added,
                        lines_removed=patched_file.removed,
                        lines_modified=patched_file.added + patched_file.removed,
                        functions_changed=functions_changed
                    )
                    diffstats.append(diffstat)
            else:
                # Fallback to basic line counting
                lines = content.split('\n')
                added = len([l for l in lines if l.startswith('+') and not l.startswith('+++')])
                removed = len([l for l in lines if l.startswith('-') and not l.startswith('---')])
                
                diffstat = DiffStat(
                    file_path=file_path,
                    lines_added=added,
                    lines_removed=removed,
                    lines_modified=added + removed,
                    functions_changed=[]
                )
                diffstats.append(diffstat)
        
        return diffstats

    def _create_markdown_diff_preview(self, files: Dict[str, str], max_lines: int = 50) -> str:
        """Create markdown-formatted diff preview for patch files"""
        preview = ""
        
        for file_path, content in files.items():
            if not file_path.endswith('.patch'):
                continue
            
            patch_set = self._parse_patch_with_unidiff(content)
            if not patch_set:
                continue
            
            preview += f"\n### 🔍 Diff Preview: {file_path.split('/')[-1]}\n\n"
            
            lines_shown = 0
            for patched_file in patch_set:
                if lines_shown >= max_lines:
                    break
                
                preview += f"**{patched_file.path}**\n"
                preview += "```diff\n"
                
                for hunk in patched_file:
                    if lines_shown >= max_lines:
                        break
                    
                    # Show hunk header with function context
                    if hunk.section_header:
                        preview += f"@@ {hunk.section_header} @@\n"
                        lines_shown += 1
                    
                    # Show actual diff lines (limited)
                    for line in hunk:
                        if lines_shown >= max_lines:
                            break
                        
                        line_content = str(line).rstrip()
                        if line_content:
                            preview += f"{line_content}\n"
                            lines_shown += 1
                
                preview += "```\n\n"
            
            if lines_shown >= max_lines:
                preview += f"*(Preview truncated at {max_lines} lines)*\n\n"
        
        return preview

    def review_sonic_patch(self, files: Dict[str, str]) -> ReviewResult:
        """Review SONiC patch files with enhanced visualization"""
        comments = []
        score = 0
        issues = []
        
        # Track review statistics
        files_reviewed = len(files)
        test_files = 0
        patch_files = 0
        python_files = 0
        
        for file_path, content in files.items():
            file_comments = self._review_file(file_path, content)
            comments.extend(file_comments)
            
            # Categorize files
            if any(__import__('re').match(pattern, file_path) for pattern in self.sonic_patterns['test_file_patterns']):
                test_files += 1
            if file_path.endswith('.patch'):
                patch_files += 1
            if file_path.endswith('.py'):
                python_files += 1
        
        # Generate diffstats for better understanding
        diffstats = self._generate_diffstat(files)
        
        # Calculate overall score based on issues found
        error_count = len([c for c in comments if c.severity == 'error'])
        warning_count = len([c for c in comments if c.severity == 'warning'])
        
        if error_count > 0:
            score = -1
            issues.append(f"{error_count} critical issues found")
        elif warning_count > 3:
            score = 0
            issues.append(f"{warning_count} warnings found")
        elif warning_count > 0:
            score = +1
            issues.append(f"{warning_count} minor warnings")
        else:
            score = +1
            issues.append("Code looks good!")
        
        # Analyze what the code does
        code_understanding = self._understand_code_changes(files)
        
        # Create clean summary 
        message = "Automated SONiC Code Review\n\n"
        
        # Add code understanding section
        if code_understanding:
            message += f"🧠 **Code Understanding:**\n{code_understanding}\n\n"
        
        # Add diff preview for patches
        diff_preview = self._create_markdown_diff_preview(files)
        if diff_preview:
            message += diff_preview
        
        if issues:
            message += "🔍 **Analysis:**\n" + "\n".join(f"- {issue}" for issue in issues)
        
        return ReviewResult(score=score, message=message, comments=comments, diffstats=diffstats)
    
    def create_upstream_prs(self, gerrit_client, change_id: str, github_token: str) -> List[str]:
        """Create upstream GitHub PRs for patches in this change"""
        try:
            from gerrit_to_pr import GerritToPRConverter
            converter = GerritToPRConverter(
                gerrit_client.gerrit_url,
                gerrit_client.username,
                gerrit_client.password, 
                github_token
            )
            return converter.process_change(change_id)
        except Exception as e:
            print(f"Failed to create upstream PRs: {e}")
            return []
    
    def _review_file(self, file_path: str, content: str) -> List[ReviewComment]:
        """Review individual file"""
        comments = []
        lines = content.split('\n')
        
        # Check if it's a test file
        is_test_file = any(
            __import__('re').match(pattern, file_path) 
            for pattern in self.sonic_patterns['test_file_patterns']
        )
        
        if is_test_file:
            comments.extend(self._review_test_file(file_path, lines))
        
        # General SONiC code review
        comments.extend(self._review_general_patterns(file_path, lines))
        
        return comments
    
    def _review_test_file(self, file_path: str, lines: List[str]) -> List[ReviewComment]:
        """Review SONiC test file specifically"""
        comments = []
        content = '\n'.join(lines)
        
        # Check for required imports
        for required_import in self.sonic_patterns['required_imports']:
            if required_import not in content:
                comments.append(ReviewComment(
                    file_path=file_path,
                    line_number=1,
                    message=f"Missing required import: {required_import}",
                    severity="warning"
                ))
        
        # Check for topology markers
        has_topology_marker = any(
            '@pytest.mark.topology' in line for line in lines
        )
        if not has_topology_marker:
            comments.append(ReviewComment(
                file_path=file_path,
                line_number=1,
                message="Missing @pytest.mark.topology decorator",
                severity="error"
            ))
        
        # Check for test function naming
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('def test_'):
                if not line.endswith(':'):
                    continue
                
                # Check for proper function parameters
                if 'duthost' not in line:
                    comments.append(ReviewComment(
                        file_path=file_path,
                        line_number=i,
                        message="Test function should include 'duthost' parameter",
                        severity="warning"
                    ))
        
        return comments
    
    def _review_general_patterns(self, file_path: str, lines: List[str]) -> List[ReviewComment]:
        """Review general code patterns"""
        comments = []
        
        for i, line in enumerate(lines, 1):
            # Check forbidden patterns
            for pattern in self.sonic_patterns['forbidden_patterns']:
                if __import__('re').search(pattern, line):
                    if 'assert' in pattern and 'pytest_assert' not in line:
                        comments.append(ReviewComment(
                            file_path=file_path,
                            line_number=i,
                            message="Use pytest_assert() instead of raw assert statements",
                            severity="error"
                        ))
                    elif 'print(' in line and 'verbose' not in line.lower():
                        # Allow print statements that are controlled by verbose flags
                        comments.append(ReviewComment(
                            file_path=file_path,
                            line_number=i,
                            message="Remove print statements from production code",
                            severity="warning"
                        ))
                    elif 'time.sleep' in line:
                        comments.append(ReviewComment(
                            file_path=file_path,
                            line_number=i,
                            message="Avoid hard-coded sleep times - use polling with timeout",
                            severity="warning"
                        ))
        
        return comments
    
    def _understand_code_changes(self, files: Dict[str, str]) -> str:
        """Analyze and understand what the code changes do"""
        understanding = []
        
        for file_path, content in files.items():
            file_analysis = self._analyze_file_purpose(file_path, content)
            if file_analysis:  # Only add non-None results
                understanding.append(file_analysis)
        
        if not understanding:
            return "This change appears to be a general maintenance or configuration update."
        
        return "\n".join(f"- {analysis}" for analysis in understanding)
    
    def _analyze_file_purpose(self, file_path: str, content: str) -> str:
        """Analyze what a specific file change does"""
        lines = content.split('\n')
        
        # Analyze patch files
        if file_path.endswith('.patch'):
            patch_type = self._analyze_patch_content(file_path, content)
            return f"Patch `{file_path.split('/')[-1]}`: {patch_type}"
        
        # Skip series file analysis - focus only on patches
        if file_path.endswith('/series'):
            return None  # Don't analyze series files
        
        # Analyze test files
        if any(__import__('re').match(pattern, file_path) for pattern in self.sonic_patterns['test_file_patterns']):
            test_functions = [line.strip() for line in lines if line.strip().startswith('def test_')]
            if test_functions:
                return f"Test file: Contains {len(test_functions)} test function(s) - {', '.join(func.replace('def ', '').split('(')[0] for func in test_functions[:2])}{'...' if len(test_functions) > 2 else ''}"
            else:
                return f"Test file modification: {file_path.split('/')[-1]}"
        
        # Analyze Python source files
        if file_path.endswith('.py'):
            functions = [line.strip() for line in lines if line.strip().startswith('def ') and not line.strip().startswith('def test_')]
            classes = [line.strip() for line in lines if line.strip().startswith('class ')]
            
            elements = []
            if functions:
                elements.append(f"{len(functions)} function(s)")
            if classes:
                elements.append(f"{len(classes)} class(es)")
            
            if elements:
                return f"Python source: {', '.join(elements)} in {file_path.split('/')[-1]}"
        
        # Default analysis
        return f"File modification: {file_path.split('/')[-1]} ({self._guess_file_type(file_path)})"
    
    def _parse_patch_with_unidiff(self, content: str) -> Optional[PatchSet]:
        """Parse patch content using unidiff library"""
        if not UNIDIFF_AVAILABLE:
            return None
        
        try:
            # The content may have embedded \n characters that need to be converted to actual newlines
            if '\\n' in content and '\n' not in content:
                content = content.replace('\\n', '\n')
            
            # Clean up the content first - extract just the diff parts
            lines = content.split('\n')
            diff_start = -1
            
            # Find where the actual diff starts
            for i, line in enumerate(lines):
                if line.startswith('diff --git') or (line.startswith('---') and i + 1 < len(lines) and lines[i + 1].startswith('+++')):
                    diff_start = i
                    break
            
            if diff_start == -1:
                print(f"DEBUG: No diff section found in patch")
                return None
            
            # Extract only the diff portion
            diff_content = '\n'.join(lines[diff_start:])
            
            # Ensure proper line endings for unidiff
            diff_lines = diff_content.splitlines(keepends=True)
            
            # Make sure we have line endings
            if diff_lines and not diff_lines[-1].endswith('\n'):
                diff_lines[-1] += '\n'
            
            result = PatchSet(diff_lines)
            print(f"DEBUG: Successfully parsed {len(result)} files with unidiff")
            return result
        except Exception as e:
            print(f"DEBUG: Failed to parse patch with unidiff: {e}")
            print(f"DEBUG: First 5 lines of content: {content.split(chr(10))[:5]}")
            return None

    def _analyze_patch_content(self, file_path: str, content: str) -> str:
        """Analyze what a patch does based on its content with enhanced diff parsing"""
        
        # Try enhanced parsing with unidiff first
        patch_set = self._parse_patch_with_unidiff(content)
        if patch_set:
            return self._analyze_patch_with_unidiff(file_path, content, patch_set)
        
        # Fallback to original string-based analysis
        return self._analyze_patch_legacy(file_path, content)
    
    def _analyze_patch_with_unidiff(self, file_path: str, content: str, patch_set: PatchSet) -> str:
        """Enhanced patch analysis using unidiff parsing"""
        analysis_parts = []
        
        # Extract subject line
        subject_line = ""
        lines = content.split('\n')
        for line in lines[:10]:
            if line.startswith('Subject:'):
                subject_line = line.replace('Subject:', '').strip()
                break
        
        # Analyze each file in the patch
        total_added = 0
        total_removed = 0
        modified_files = []
        function_changes = []
        
        for patched_file in patch_set:
            file_added = patched_file.added
            file_removed = patched_file.removed
            total_added += file_added
            total_removed += file_removed
            
            file_name = patched_file.path
            modified_files.append(file_name)
            
            # Extract function context from hunks
            for hunk in patched_file:
                if hunk.section_header:
                    func_name = hunk.section_header.strip()
                    if func_name not in function_changes:
                        function_changes.append(func_name)
        
        # Build semantic analysis
        if subject_line:
            if 'enable kdump by default' in subject_line.lower():
                analysis_parts.append("Enables kdump crash dump collection by default without requiring reboot")
            elif 'cleanup crashkernel' in subject_line.lower():
                analysis_parts.append("Improves kdump cleanup functionality to handle kernel-cmdline-append files")
            else:
                analysis_parts.append(f'"{subject_line}"')
        
        # Add file-specific analysis
        for file_name in modified_files:
            if '.py' in file_name:
                analysis_parts.append(f"modifies Python code in {file_name}")
            elif 'build_image.sh' in file_name:
                analysis_parts.append(f"updates build script {file_name}")
            elif 'Makefile' in file_name or 'rules/config' in file_name:
                analysis_parts.append(f"changes build configuration in {file_name}")
        
        # Add function-level changes if available
        if function_changes:
            funcs_str = ', '.join(function_changes[:3])
            if len(function_changes) > 3:
                funcs_str += f" (+{len(function_changes) - 3} more)"
            analysis_parts.append(f"affects functions: {funcs_str}")
        
        # Add diffstat
        if total_added or total_removed:
            analysis_parts.append(f"(+{total_added}/-{total_removed} lines)")
        
        return ", ".join(analysis_parts) if analysis_parts else "Patch modification"
    
    def _analyze_patch_legacy(self, file_path: str, content: str) -> str:
        """Enhanced manual patch analysis that actually works with Gerrit's format"""
        
        # Handle content that may have embedded newlines
        if '\\n' in content:
            content = content.replace('\\n', '\n')
        
        lines = content.split('\n')
        
        # Extract subject line and description
        subject_line = ""
        description = ""
        for i, line in enumerate(lines[:15]):
            if line.startswith('Subject:'):
                subject_line = line.replace('Subject:', '').strip()
            elif subject_line and not line.strip() and i + 1 < len(lines):
                # Next non-empty line after subject is description
                next_line = lines[i + 1].strip()
                if next_line and not next_line.startswith('---') and not next_line.startswith('diff'):
                    description = next_line
                    break
        
        # Extract modified files and changes
        modified_files = []
        added_lines = []
        removed_lines = []
        current_file = None
        
        for line in lines:
            # Look for file changes
            if line.startswith('diff --git'):
                parts = line.split()
                if len(parts) >= 4:
                    current_file = parts[3].replace('b/', '')
                    if current_file not in modified_files:
                        modified_files.append(current_file)
            elif line.startswith('+++'):
                parts = line.split()
                if len(parts) >= 2:
                    current_file = parts[1].replace('b/', '')
                    if current_file not in modified_files:
                        modified_files.append(current_file)
            elif line.startswith('+') and not line.startswith('+++'):
                added_content = line[1:].strip()
                if added_content:  # Ignore empty lines
                    added_lines.append(added_content)
            elif line.startswith('-') and not line.startswith('---'):
                removed_content = line[1:].strip()
                if removed_content:  # Ignore empty lines
                    removed_lines.append(removed_content)
        
        # Build meaningful analysis
        analysis_parts = []
        
        # Use subject line for primary description
        if subject_line:
            analysis_parts.append(subject_line)
        
        # Add specific file analysis
        for file_name in modified_files:
            if 'build_image.sh' in file_name:
                # Look for specific changes in build script
                crashkernel_added = [line for line in added_lines if 'crashkernel=' in line]
                if crashkernel_added:
                    for line in crashkernel_added:
                        if 'crashkernel=' in line:
                            import re
                            match = re.search(r'crashkernel=([^\s"]+)', line)
                            if match:
                                analysis_parts.append(f"adds crashkernel memory allocation: {match.group(1)}")
                else:
                    analysis_parts.append(f"modifies build script {file_name}")
            elif 'sonic-kdump-config' in file_name:
                # Look for function additions
                new_functions = [line for line in added_lines if line.startswith('def ')]
                if new_functions:
                    func_names = [line.split('(')[0].replace('def ', '') for line in new_functions]
                    analysis_parts.append(f"adds functions: {', '.join(func_names)}")
                else:
                    analysis_parts.append(f"updates kdump configuration script")
            else:
                analysis_parts.append(f"modifies {file_name}")
        
        # Add diffstat
        if added_lines or removed_lines:
            analysis_parts.append(f"(+{len(added_lines)}/-{len(removed_lines)} lines)")
        
        return ", ".join(analysis_parts) if analysis_parts else "Patch modification"
    
    def _guess_file_type(self, file_path: str) -> str:
        """Guess file type from path"""
        if file_path.endswith('.py'):
            return 'Python'
        elif file_path.endswith('.patch'):
            return 'Patch'
        elif file_path.endswith('.sh'):
            return 'Shell script'
        elif file_path.endswith('.yml') or file_path.endswith('.yaml'):
            return 'YAML'
        elif file_path.endswith('.json'):
            return 'JSON'
        elif '/series' in file_path:
            return 'Patch series'
        else:
            return 'Configuration'


class GerritReviewPlugin:
    """Main plugin class"""
    
    def __init__(self, config_file: str = None):
        self.config = self._load_config(config_file)
        self.gerrit_client = GerritClient(
            self.config['gerrit_url'],
            self.config['username'],
            self.config['password']
        )
        self.reviewer = SONiCCodeReviewer()
    
    def update_gerrit_description(self, change_id: str, review_summary: str, pr_urls: List[str] = None):
        """Update Gerrit change description with review summary and PR links"""
        try:
            # Get current change details
            change_details = self.gerrit_client.get_change_details(change_id)
            current_msg = change_details.get('subject', '')
            
            # Create enhanced description
            description = f"**Automated SONiC Code Review Summary:**\n\n{review_summary}"
            
            if pr_urls:
                description += f"\n\n**🚀 Draft Pull Requests Created:**\n"
                for url in pr_urls:
                    description += f"- {url}\n"
                description += "\n⚠️ *PRs are in DRAFT mode for internal review*"
            
            # Update change description via commit message amendment
            url = f"{self.gerrit_client.gerrit_url}/a/changes/{change_id}/revisions/current/review"
            data = {
                "message": f"🤖 **Automated Review Completed**\n\n{description}",
                "notify": "OWNER"
            }
            
            response = self.gerrit_client.session.post(url, json=data)
            if response.status_code == 200:
                print(f"✅ Updated Gerrit description with review summary and PR links")
            else:
                print(f"⚠️ Failed to update Gerrit description: {response.status_code}")
                
        except Exception as e:
            print(f"⚠️ Failed to update Gerrit description: {e}")
    
    def _load_config(self, config_file: str) -> Dict:
        """Load plugin configuration"""
        if config_file and os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return json.load(f)
        
        # Default configuration
        return {
            'gerrit_url': os.getenv('GERRIT_URL', 'https://gerrit.corp.arista.io'),
            'username': os.getenv('GERRIT_USERNAME', ''),
            'password': os.getenv('GERRIT_PASSWORD', ''),
            'auto_submit': False,
            'review_score_threshold': 1
        }
    
    def review_change(self, change_id: str, submit_review: bool = False, create_prs: bool = False, github_token: str = None) -> ReviewResult:
        """Review a Gerrit change and optionally create upstream PRs"""
        print(f"Reviewing change {change_id}...")
        
        # Get change details
        change_details = self.gerrit_client.get_change_details(change_id)
        
        # Handle different revision field names
        current_revision = None
        if 'current_revision' in change_details:
            current_revision = change_details['current_revision']
        elif 'current_revision_number' in change_details:
            # Use current revision number as string
            current_revision = str(change_details['current_revision_number'])
        elif 'revisions' in change_details:
            # Get the latest revision
            revisions = change_details['revisions']
            current_revision = max(revisions.keys())
        else:
            # Fallback to 'current' which works with many Gerrit APIs
            current_revision = 'current'
            print("Warning: Using 'current' as revision ID")
        
        print(f"Using revision: {current_revision}")
        
        # Get files in the change
        files_info = self.gerrit_client.get_change_files(change_id, current_revision)
        
        # Download and analyze files
        files_content = {}
        for file_path in files_info.keys():
            if file_path == '/COMMIT_MSG':
                continue
            try:
                content = self.gerrit_client.get_file_content(change_id, current_revision, file_path)
                files_content[file_path] = content
                
                # Debug: Show first few lines of patch content (disabled for cleaner output)
                # if file_path.endswith('.patch'):
                #     print(f"DEBUG: First 3 lines of {file_path}:")
                #     first_lines = content.split('\n')[:3]
                #     for i, line in enumerate(first_lines, 1):
                #         print(f"  {i}: {line}")
            except Exception as e:
                print(f"Warning: Could not retrieve {file_path}: {e}")
        
        # Perform review
        review_result = self.reviewer.review_sonic_patch(files_content)
        
        # Create upstream PRs if requested
        pr_urls = []
        if create_prs and github_token:
            print("\n🚀 Creating upstream draft PRs...")
            pr_urls = self.reviewer.create_upstream_prs(self.gerrit_client, change_id, github_token)
        
        # Update Gerrit description with review summary and PR links
        if create_prs or submit_review:
            self.update_gerrit_description(change_id, review_result.message, pr_urls)
        
        # Submit review if requested
        if submit_review:
            success = self.gerrit_client.submit_review(change_id, current_revision, review_result)
            if success:
                print("Review submitted successfully!")
            else:
                print("Failed to submit review")
        
        return review_result
    
    def create_config_template(self, output_path: str = 'gerrit_config.json'):
        """Create configuration template"""
        template = {
            "gerrit_url": "https://gerrit.corp.arista.io",
            "username": "your_username",
            "password": "your_http_password",
            "auto_submit": False,
            "review_score_threshold": 1,
            "sonic_specific_checks": {
                "require_test_updates": True,
                "check_patch_format": True,
                "validate_commit_message": True
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(template, f, indent=2)
        
        print(f"Configuration template created: {output_path}")
        print("Please update with your Gerrit credentials and preferences.")


def main():
    parser = argparse.ArgumentParser(description='Gerrit Code Review Plugin')
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--change-id', help='Gerrit change ID to review')
    parser.add_argument('--submit', action='store_true', help='Submit review after analysis')
    parser.add_argument('--create-config', action='store_true', help='Create configuration template')
    parser.add_argument('--create-prs', action='store_true', help='Create upstream GitHub draft PRs')
    parser.add_argument('--github-token', help='GitHub personal access token for creating PRs')
    
    args = parser.parse_args()
    
    if args.create_config:
        plugin = GerritReviewPlugin()
        plugin.create_config_template()
        return
    
    if not args.change_id:
        print("Error: --change-id is required")
        sys.exit(1)
    
    try:
        plugin = GerritReviewPlugin(args.config)
        
        # Check for PR creation requirements
        if args.create_prs and not args.github_token:
            print("Error: --github-token required when using --create-prs")
            sys.exit(1)
        
        result = plugin.review_change(
            args.change_id, 
            submit_review=args.submit,
            create_prs=args.create_prs,
            github_token=args.github_token
        )
        
        print(f"\nReview Result:")
        print(f"Score: {result.score}")
        print(f"Message: {result.message}")
        
        if result.comments:
            print(f"\nComments ({len(result.comments)}):")
            for comment in result.comments:
                print(f"  {comment.file_path}:{comment.line_number} [{comment.severity}] {comment.message}")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
