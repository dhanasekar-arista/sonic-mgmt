#!/usr/bin/env python3
"""
Enhanced Gerrit Review Plugin with SONiC Functional Analysis

This is an enhanced version that includes both the base plugin and functional
analysis in a single file to avoid import issues.
"""

import os
import sys
import json
import requests
import argparse
import re
import base64
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from abc import ABC, abstractmethod

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


# ============================================================================
# SONIC KNOWLEDGE BASE AND RULE ENGINE
# ============================================================================

class KnowledgeBase:
    """SONiC domain knowledge repository"""

    def __init__(self):
        # Core SONiC DB tables
        self.db_tables = {
            "STATE_DB", "CONFIG_DB", "APPL_DB", "COUNTERS_DB", "ASIC_DB", 
            "LOGLEVEL_DB", "FLEX_COUNTER_DB", "ERROR_DB", "USER_DB"
        }

        # Config DB table prefixes
        self.config_db_tables = {
            "PORT", "VLAN", "VLAN_INTERFACE", "VLAN_MEMBER", "LAG", "INTERFACE",
            "LOOPBACK_INTERFACE", "BGP_NEIGHBOR", "DEVICE_METADATA", "ACL_TABLE"
        }

        # Warm reboot indicators
        self.warm_restart_tokens = {
            "warm_restart_enable", "WARM_RESTART_ENABLE", "warm-reboot",
            "warmRestoreContext", "isWarmStart", "WARM_RESTART_TABLE"
        }

        # Component patterns
        self.component_patterns = {
            "orchagent": re.compile(r"orchagent/.*\.cpp"),
            "syncd": re.compile(r"syncd/.*\.cpp"),  
            "platform": re.compile(r"platform/.*\.py"),
            "test": re.compile(r"tests/.*\.py"),
            "cli": re.compile(r"(scripts/|utilities/).*\.py")
        }

    def get_component_type(self, file_path: str) -> str:
        """Identify SONiC component from file path"""
        for component, pattern in self.component_patterns.items():
            if pattern.search(file_path):
                return component
        return "unknown"

    def is_reboot_sensitive(self, file_path: str) -> bool:
        """Check if file affects warm reboot behavior"""
        sensitive_patterns = [
            r"warm.*reboot", r"systemd/.*\.service", r"orchagent/.*orch\.cpp",
            r"syncd/", r"scripts/(reboot|restart)"
        ]
        return any(re.search(pattern, file_path, re.I) for pattern in sensitive_patterns)


class BaseRule(ABC):
    """Base class for functional review rules"""
    
    description = "Base SONiC rule"
    
    @abstractmethod
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        """Analyze a patched file and return review comments"""
        pass


class WarmRebootRule(BaseRule):
    """Check warm reboot safety and state restoration"""
    
    description = "Verify warm reboot handling"

    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        
        if not kb.is_reboot_sensitive(patched_file.path):
            return comments

        # Check if patch includes warm reboot logic
        has_warm_logic = False
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    if any(token in line.value for token in kb.warm_restart_tokens):
                        has_warm_logic = True
                        break

        if not has_warm_logic:
            comments.append(ReviewComment(
                file_path=patched_file.path,
                line_number=1,
                message="Change affects reboot-sensitive component but doesn't include warm restart logic. Verify warm reboot behavior and state recovery.",
                severity="warning"
            ))

        return comments


class DBSchemaRule(BaseRule):
    """Validate DB table usage patterns"""
    
    description = "Check DB schema consistency"
    
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    # Check for unknown DB table references
                    db_matches = re.findall(r'"?(\w+_DB)"?', line.value)
                    for table in db_matches:
                        if table not in kb.db_tables:
                            comments.append(ReviewComment(
                                file_path=patched_file.path,
                                line_number=line.target_line_no or 1,
                                message=f"Unknown DB table '{table}' referenced. Verify table exists in SONiC DB schema.",
                                severity="error"
                            ))

        return comments


class TestQualityRule(BaseRule):
    """Analyze test quality and patterns"""
    
    description = "Check test implementation quality"
    
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        
        if kb.get_component_type(patched_file.path) != "test":
            return comments

        added_content = ""
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    added_content += line.value + "\n"

        # Check for test improvements
        if "allowed_disruption" in added_content:
            comments.append(ReviewComment(
                file_path=patched_file.path,
                line_number=1,
                message="Test disruption tolerance added. Good practice for flaky test stabilization.",
                severity="info"
            ))

        if "delay=" in added_content and "disruption" in added_content:
            comments.append(ReviewComment(
                file_path=patched_file.path,
                line_number=1,
                message="Test timing parameters adjusted for better stability. Verify delay values are appropriate for test environment.",
                severity="info"
            ))

        return comments


class RuleEngine:
    """SONiC functional review rule engine"""
    
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb or KnowledgeBase()
        self.rules = [
            WarmRebootRule(),
            DBSchemaRule(),
            TestQualityRule(),
        ]
    
    def analyze_patchset(self, patch_set) -> List[ReviewComment]:
        """Run all rules and return functional review comments"""
        all_comments = []
        
        for patched_file in patch_set:
            if patched_file.is_removed_file or patched_file.is_binary_file:
                continue
            
            for rule in self.rules:
                try:
                    comments = rule.check(patched_file, self.kb)
                    all_comments.extend(comments)
                except Exception as e:
                    print(f"Warning: Rule {rule.__class__.__name__} failed: {e}")
        
        return all_comments


# ============================================================================
# ENHANCED GERRIT CLIENT AND REVIEWER
# ============================================================================

class GerritClient:
    """Enhanced Gerrit REST API client with better content handling"""
    
    def __init__(self, gerrit_url: str, username: str, password: str):
        self.gerrit_url = gerrit_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.auth = (username, password)
    
    def get_change_details(self, change_id: str) -> Dict:
        """Get change details from Gerrit"""
        url = f"{self.gerrit_url}/a/changes/{change_id}/detail"
        response = self.session.get(url)
        if response.status_code == 200:
            response_text = response.text
            if response_text.startswith(")]}'\n"):
                response_text = response_text[5:]
            return json.loads(response_text)
        else:
            raise Exception(f"Failed to get change details: {response.status_code}")
    
    def get_change_files(self, change_id: str, revision_id: str = 'current') -> Dict:
        """Get list of files in a change"""
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/files"
        response = self.session.get(url)
        if response.status_code == 200:
            response_text = response.text
            if response_text.startswith(")]}'\n"):
                response_text = response_text[5:]
            return json.loads(response_text)
        else:
            raise Exception(f"Failed to get change files: {response.status_code}")
    
    def get_file_content(self, change_id: str, revision_id: str, file_path: str) -> str:
        """Get file content with enhanced decoding"""
        import urllib.parse
        encoded_file_path = urllib.parse.quote(file_path, safe='')
        url = f"{self.gerrit_url}/a/changes/{change_id}/revisions/{revision_id}/files/{encoded_file_path}/content"
        
        response = self.session.get(url)
        if response.status_code == 200:
            response_text = response.text
            
            # Remove Gerrit prefix
            if response_text.startswith(")]}'\n"):
                response_text = response_text[5:]
            
            # Handle JSON-escaped content (most common case)
            if response_text.startswith('"') and response_text.endswith('"'):
                try:
                    # This is JSON-escaped content
                    decoded = json.loads(response_text)
                    return decoded
                except json.JSONDecodeError:
                    pass
            
            # Try base64 decode
            try:
                missing_padding = len(response_text) % 4
                if missing_padding:
                    response_text += '=' * (4 - missing_padding)
                return base64.b64decode(response_text).decode('utf-8')
            except:
                # Return as-is if all decoding fails
                return response_text
        else:
            raise Exception(f"Failed to get file content: {response.status_code}")


class SONiCFunctionalReviewer:
    """Enhanced SONiC code reviewer with functional analysis"""
    
    def __init__(self):
        self.kb = KnowledgeBase()
        self.rule_engine = RuleEngine(self.kb)
    
    def review_patches(self, files: Dict[str, str]) -> ReviewResult:
        """Review patches with functional analysis"""
        all_comments = []
        diffstats = []
        
        # Process each patch file
        for file_path, content in files.items():
            if not file_path.endswith('.patch'):
                continue
            
            # Parse patch with unidiff
            patch_set = self._parse_patch(content)
            if patch_set:
                # Run functional analysis
                functional_comments = self.rule_engine.analyze_patchset(patch_set)
                all_comments.extend(functional_comments)
                
                # Generate diffstat
                for patched_file in patch_set:
                    diffstat = DiffStat(
                        file_path=patched_file.path,
                        lines_added=patched_file.added,
                        lines_removed=patched_file.removed,
                        lines_modified=patched_file.added + patched_file.removed,
                        functions_changed=[]
                    )
                    diffstats.append(diffstat)
        
        # Calculate score
        error_count = len([c for c in all_comments if c.severity == 'error'])
        warning_count = len([c for c in all_comments if c.severity == 'warning'])
        info_count = len([c for c in all_comments if c.severity == 'info'])
        
        if error_count > 0:
            score = -1
        elif warning_count > 3:
            score = 0
        elif warning_count > 0:
            score = +1
        else:
            score = +1
        
        # Create meaningful message
        message = "🤖 **SONiC Functional Code Review**\n\n"
        
        if error_count > 0 or warning_count > 0 or info_count > 0:
            message += "**🔍 Functional Analysis:**\n"
            if error_count > 0:
                message += f"- 🚨 {error_count} architectural issues\n"
            if warning_count > 0:
                message += f"- ⚠️ {warning_count} design concerns\n"
            if info_count > 0:
                message += f"- ℹ️ {info_count} recommendations\n"
            message += "\n"
        
        # Add diff preview
        diff_preview = self._create_diff_preview(files)
        if diff_preview:
            message += diff_preview
        
        return ReviewResult(score=score, message=message, comments=all_comments, diffstats=diffstats)
    
    def _parse_patch(self, content: str) -> Optional[PatchSet]:
        """Parse patch content with enhanced handling"""
        if not UNIDIFF_AVAILABLE:
            return None
        
        try:
            # Handle JSON-escaped content
            if content.startswith('"') and content.endswith('"'):
                content = json.loads(content)
            
            # Convert embedded newlines
            if '\\n' in content:
                content = content.replace('\\n', '\n')
            
            # Find diff section
            lines = content.split('\n')
            diff_start = -1
            
            for i, line in enumerate(lines):
                if line.startswith('diff --git'):
                    diff_start = i
                    break
            
            if diff_start == -1:
                return None
            
            # Extract diff and parse
            diff_content = '\n'.join(lines[diff_start:])
            diff_lines = diff_content.splitlines(keepends=True)
            
            return PatchSet(diff_lines)
        except Exception as e:
            print(f"DEBUG: Patch parsing failed: {e}")
            return None
    
    def _create_diff_preview(self, files: Dict[str, str]) -> str:
        """Create readable diff preview"""
        preview = ""
        
        for file_path, content in files.items():
            if not file_path.endswith('.patch'):
                continue
            
            patch_set = self._parse_patch(content)
            if not patch_set:
                continue
            
            preview += f"\n### 🔍 {file_path.split('/')[-1]}\n\n"
            
            for patched_file in patch_set:
                preview += f"**{patched_file.path}** (+{patched_file.added}/-{patched_file.removed} lines)\n"
                preview += "```diff\n"
                
                # Show limited diff content
                line_count = 0
                for hunk in patched_file:
                    for line in hunk:
                        if line_count >= 20:  # Limit output
                            break
                        preview += str(line).rstrip() + "\n"
                        line_count += 1
                    if line_count >= 20:
                        break
                
                preview += "```\n\n"
        
        return preview


# ============================================================================
# RULE IMPLEMENTATIONS
# ============================================================================

class WarmRebootRule(BaseRule):
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        
        if not kb.is_reboot_sensitive(patched_file.path):
            return comments

        has_warm_logic = False
        for hunk in patched_file:
            for line in hunk:
                if line.is_added and any(token in line.value for token in kb.warm_restart_tokens):
                    has_warm_logic = True
                    break

        if not has_warm_logic:
            comments.append(ReviewComment(
                file_path=patched_file.path,
                line_number=1,
                message="Change affects reboot-sensitive component but doesn't include warm restart logic. Verify warm reboot behavior.",
                severity="warning"
            ))

        return comments


class TestQualityRule(BaseRule):
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        
        if kb.get_component_type(patched_file.path) != "test":
            return comments

        # Analyze test improvements
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    if "allowed_disruption" in line.value:
                        comments.append(ReviewComment(
                            file_path=patched_file.path,
                            line_number=line.target_line_no or 1,
                            message="Test disruption tolerance added - good practice for flaky test stabilization.",
                            severity="info"
                        ))
                    
                    if "delay=" in line.value and "MUX_SIM" in line.value:
                        comments.append(ReviewComment(
                            file_path=patched_file.path,
                            line_number=line.target_line_no or 1,
                            message="MUX simulation timing adjusted. Verify delay values match expected hardware behavior.",
                            severity="info"
                        ))

        return comments


class RuleEngine:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.rules = [WarmRebootRule(), TestQualityRule()]
    
    def analyze_patchset(self, patch_set) -> List[ReviewComment]:
        all_comments = []
        for patched_file in patch_set:
            for rule in self.rules:
                comments = rule.check(patched_file, self.kb)
                all_comments.extend(comments)
        return all_comments


# ============================================================================
# MAIN PLUGIN
# ============================================================================

def review_change(change_id: str, config_file: str = None) -> ReviewResult:
    """Review a Gerrit change with functional analysis"""
    
    # Load configuration
    config = {'gerrit_url': 'https://gerrit.corp.arista.io', 'username': '', 'password': ''}
    if config_file and os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config.update(json.load(f))
    
    # Initialize clients
    gerrit_client = GerritClient(config['gerrit_url'], config['username'], config['password'])
    reviewer = SONiCFunctionalReviewer()
    
    print(f"Reviewing change {change_id} with functional analysis...")
    
    # Get change details
    change_details = gerrit_client.get_change_details(change_id)
    revision_id = str(change_details.get('current_revision_number', 'current'))
    
    # Get files
    files_info = gerrit_client.get_change_files(change_id, revision_id)
    
    # Download patch files
    files_content = {}
    for file_path in files_info.keys():
        if file_path == '/COMMIT_MSG':
            continue
        try:
            content = gerrit_client.get_file_content(change_id, revision_id, file_path)
            files_content[file_path] = content
            print(f"Successfully retrieved: {file_path}")
        except Exception as e:
            print(f"Warning: Could not retrieve {file_path}: {e}")
    
    # Perform functional review
    return reviewer.review_patches(files_content)


def main():
    parser = argparse.ArgumentParser(description='SONiC Functional Gerrit Review')
    parser.add_argument('--change-id', required=True, help='Gerrit change ID')
    parser.add_argument('--config', help='Configuration file path')
    
    args = parser.parse_args()
    
    try:
        result = review_change(args.change_id, args.config)
        
        print(f"\nFunctional Review Result:")
        print(f"Score: {result.score}")
        print(f"Message:\n{result.message}")
        
        if result.comments:
            print(f"\nFunctional Comments ({len(result.comments)}):")
            for comment in result.comments:
                print(f"  {comment.file_path}:{comment.line_number} [{comment.severity}] {comment.message}")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
