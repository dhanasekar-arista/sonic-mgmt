#!/usr/bin/env python3
"""
SONiC functional rule engine.

All SONiC-specific rules live here. Any rule only needs to:
   • inherit from BaseRule
   • implement `check(self, patched_file, kb) -> list[ReviewComment]`
"""

import re
from pathlib import PurePosixPath
from typing import List, Dict, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

# Import ReviewComment from the main plugin
try:
    from gerrit_review_plugin import ReviewComment
except ImportError:
    # Fallback definition if imported separately
    @dataclass
    class ReviewComment:
        file_path: str
        line_number: int
        message: str
        severity: str


class KnowledgeBase:
    """
    SONiC domain knowledge repository.
    Contains architectural facts, design patterns, and common pitfalls.
    """

    def __init__(self) -> None:
        # DB tables officially documented
        self.db_tables: set[str] = {
            "STATE_DB", "CONFIG_DB", "APPL_DB", "COUNTERS_DB", "ASIC_DB", 
            "LOGLEVEL_DB", "FLEX_COUNTER_DB", "ERROR_DB", "USER_DB",
            "CHASSIS_APP_DB", "CHASSIS_STATE_DB"
        }

        # DB table prefixes that require special handling
        self.config_db_tables = {
            "PORT", "VLAN", "VLAN_INTERFACE", "VLAN_MEMBER", "LAG", "INTERFACE",
            "LOOPBACK_INTERFACE", "BGP_NEIGHBOR", "DEVICE_METADATA", "ACL_TABLE",
            "ACL_RULE", "MIRROR_SESSION", "POLICER", "WRED_PROFILE", "SCHEDULER"
        }

        # Key-spaces that should not be accessed directly
        self.forbidden_raw_redis_prefix: set[str] = {
            "COUNTERS_DB", "ASIC_DB"
        }

        # Canonical warm reboot indicators
        self.warm_restart_tokens: set[str] = {
            "warm_restart_enable", "WARM_RESTART_ENABLE", "warm-reboot",
            "systemctl reload-or-restart", "warmRestoreContext", "warmBootHelper",
            "WARM_RESTART_TABLE", "warm_start", "isWarmStart"
        }

        # Required DB access patterns
        self.required_db_wrappers: set[str] = {
            "swsscommon", "sonic_py_common", "SonicV2Connector", "ConfigDBConnector",
            "ProducerStateTable", "ConsumerStateTable", "SubscriberStateTable"
        }

        # Critical SONiC services
        self.critical_services = {
            "swss", "syncd", "bgp", "teamd", "lldp", "snmp", "telemetry",
            "nat", "dhcp_relay", "radv", "mgmt-framework"
        }

        # Orchestrator classes that need specific patterns
        self.orch_classes = {
            "PortsOrch", "NeighOrch", "RouteOrch", "FdbOrch", "AclOrch",
            "TunnelOrch", "Policer", "QosOrch", "BufferOrch", "MirrorOrch"
        }

        # File path patterns for different components
        self.component_patterns = {
            "orchagent": re.compile(r"orchagent/.*\.cpp"),
            "syncd": re.compile(r"syncd/.*\.cpp"),
            "platform": re.compile(r"platform/.*\.py"),
            "cli": re.compile(r"(scripts/|utilities/).*\.py"),
            "config": re.compile(r".*config.*\.(json|yaml|yml)"),
            "systemd": re.compile(r".*\.service$")
        }

    def get_component_type(self, file_path: str) -> str:
        """Identify which SONiC component this file belongs to"""
        for component, pattern in self.component_patterns.items():
            if pattern.search(file_path):
                return component
        return "unknown"

    def is_critical_service(self, service_name: str) -> bool:
        return service_name in self.critical_services

    def is_db_table(self, token: str) -> bool:
        return token in self.db_tables

    def is_config_db_table(self, token: str) -> bool:
        return token in self.config_db_tables

    def is_reboot_sensitive(self, file_path: str) -> bool:
        """Check if file path indicates reboot-sensitive component"""
        sensitive_patterns = [
            r"warm.*reboot", r"systemd/.*\.service", r"orchagent/.*orch\.cpp",
            r"syncd/", r"scripts/(reboot|restart)"
        ]
        return any(re.search(pattern, file_path, re.I) for pattern in sensitive_patterns)


class BaseRule(ABC):
    """Base class for all SONiC functional review rules"""
    
    description = "Base SONiC rule"
    
    @abstractmethod
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        """Analyze a patched file and return review comments"""
        pass


class WarmRebootRule(BaseRule):
    """Verify warm reboot handling in reboot-sensitive changes"""
    
    description = "Check warm reboot safety and state restoration logic"

    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        file_path = patched_file.path

        if not kb.is_reboot_sensitive(file_path):
            return comments

        # Check if patch adds warm reboot handling
        has_warm_logic = False
        added_lines = []
        
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    added_lines.append(line.value)
                    if any(token in line.value for token in kb.warm_restart_tokens):
                        has_warm_logic = True

        if not has_warm_logic and added_lines:
            comments.append(ReviewComment(
                file_path=file_path,
                line_number=1,
                message="Change affects reboot-sensitive component but doesn't reference warm restart logic. Verify warm reboot behavior and state recovery.",
                severity="warning"
            ))

        return comments


class DBSchemaRule(BaseRule):
    """Detect DB schema inconsistencies and access pattern violations"""
    
    description = "Validate DB table usage and schema consistency"
    
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        
        for hunk in patched_file:
            for line in hunk:
                if not line.is_added:
                    continue
                
                # Check for unknown DB table references
                db_matches = re.findall(r'"?(\w+_DB)"?', line.value)
                for table in db_matches:
                    if not kb.is_db_table(table):
                        comments.append(ReviewComment(
                            file_path=patched_file.path,
                            line_number=line.target_line_no or 1,
                            message=f"Unknown DB table '{table}' referenced. Verify table exists in SONiC DB schema.",
                            severity="error"
                        ))
                
                # Check for raw redis usage on restricted tables
                if "import redis" in line.value or "redis.Redis" in line.value:
                    # Look for forbidden table access in surrounding context
                    for forbidden in kb.forbidden_raw_redis_prefix:
                        if forbidden in line.value:
                            comments.append(ReviewComment(
                                file_path=patched_file.path,
                                line_number=line.target_line_no or 1,
                                message=f"Direct redis access to {forbidden} detected. Use swsscommon interface (ConfigDBConnector, etc.) instead.",
                                severity="warning"
                            ))

        return comments


class ConcurrencyRule(BaseRule):
    """Detect concurrency issues and missing synchronization"""
    
    description = "Check thread safety and synchronization patterns"
    
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        
        # Collect all added lines to analyze patterns
        added_content = ""
        thread_introduced = False
        lock_present = False
        
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    added_content += line.value + "\n"
        
        # Check for threading without synchronization
        thread_patterns = [r'\bThread\(', r'\bthreading\.', r'\bpthread_create']
        lock_patterns = [r'\bLock\(', r'\bmutex', r'\bRLock', r'\bSemaphore']
        
        for pattern in thread_patterns:
            if re.search(pattern, added_content):
                thread_introduced = True
                break
        
        for pattern in lock_patterns:
            if re.search(pattern, added_content):
                lock_present = True
                break
        
        if thread_introduced and not lock_present:
            comments.append(ReviewComment(
                file_path=patched_file.path,
                line_number=1,
                message="Threading introduced but no synchronization primitives found. Review shared resource access for race conditions.",
                severity="warning"
            ))

        # Check for potential race conditions in DB access
        if "CONFIG_DB" in added_content and "STATE_DB" in added_content:
            comments.append(ReviewComment(
                file_path=patched_file.path,
                line_number=1,
                message="Patch modifies both CONFIG_DB and STATE_DB. Ensure proper ordering and consistency during updates.",
                severity="info"
            ))

        return comments


class SONiCDesignPatternRule(BaseRule):
    """Validate adherence to SONiC design patterns and best practices"""
    
    description = "Check SONiC architectural patterns and conventions"
    
    def check(self, patched_file, kb: KnowledgeBase) -> List[ReviewComment]:
        comments = []
        file_path = patched_file.path
        component = kb.get_component_type(file_path)
        
        # Orchestrator class pattern validation
        if component == "orchagent":
            self._check_orch_patterns(patched_file, kb, comments)
        
        # Platform API pattern validation
        if component == "platform":
            self._check_platform_patterns(patched_file, kb, comments)
        
        # CLI pattern validation  
        if component == "cli":
            self._check_cli_patterns(patched_file, kb, comments)
        
        return comments
    
    def _check_orch_patterns(self, patched_file, kb: KnowledgeBase, comments: List[ReviewComment]):
        """Check orchestrator-specific patterns"""
        added_content = ""
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    added_content += line.value + "\n"
        
        # Check for new Orch class without proper registration
        if "class " in added_content and "Orch" in added_content:
            if "addConsumer" not in added_content and "TableConsumer" not in added_content:
                comments.append(ReviewComment(
                    file_path=patched_file.path,
                    line_number=1,
                    message="New Orch class detected. Ensure it's properly registered with addConsumer() and has TableConsumer setup.",
                    severity="warning"
                ))
    
    def _check_platform_patterns(self, patched_file, kb: KnowledgeBase, comments: List[ReviewComment]):
        """Check platform API patterns"""
        for hunk in patched_file:
            for line in hunk:
                if line.is_added and "def " in line.value:
                    # Check for platform API version compliance
                    if "get_" in line.value or "set_" in line.value:
                        # This looks like a platform API method
                        if "PLATFORM_API_VERSION" not in patched_file.path:
                            comments.append(ReviewComment(
                                file_path=patched_file.path,
                                line_number=line.target_line_no or 1,
                                message="New platform API method detected. Verify PLATFORM_API_VERSION compatibility and mandatory method implementation.",
                                severity="info"
                            ))
    
    def _check_cli_patterns(self, patched_file, kb: KnowledgeBase, comments: List[ReviewComment]):
        """Check CLI command patterns"""
        added_content = ""
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    added_content += line.value + "\n"
        
        # Check for CLI commands without proper error handling
        if "@click.command" in added_content or "def cli_" in added_content:
            if "try:" not in added_content and "except" not in added_content:
                comments.append(ReviewComment(
                    file_path=patched_file.path,
                    line_number=1,
                    message="New CLI command without exception handling. Add try/except blocks for robust error handling.",
                    severity="info"
                ))


class RuleEngine:
    """Orchestrates all SONiC functional review rules"""
    
    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb or KnowledgeBase()
        self.rules: List[BaseRule] = [
            WarmRebootRule(),
            DBSchemaRule(),
            ConcurrencyRule(),
            SONiCDesignPatternRule(),
        ]
    
    def analyze_patchset(self, patch_set) -> List[ReviewComment]:
        """Run all rules against a patchset and return combined feedback"""
        all_comments = []
        
        for patched_file in patch_set:
            # Skip deleted or binary files
            if patched_file.is_removed_file or patched_file.is_binary_file:
                continue
            
            # Run all rules on this file
            for rule in self.rules:
                try:
                    file_comments = rule.check(patched_file, self.kb)
                    all_comments.extend(file_comments)
                except Exception as e:
                    # Don't let one rule failure break entire review
                    print(f"Warning: Rule {rule.__class__.__name__} failed on {patched_file.path}: {e}")
        
        return all_comments
    
    def get_rule_summary(self) -> str:
        """Return summary of active rules for debugging"""
        rule_names = [rule.__class__.__name__ for rule in self.rules]
        return f"Active rules: {', '.join(rule_names)}"


# Quick self-test function
def self_test():
    """Test the rule engine with sample diff"""
    try:
        from unidiff import PatchSet
        
        demo_diff = """diff --git a/scripts/warm-reboot b/scripts/warm-reboot
index 111..222 100644
--- a/scripts/warm-reboot
+++ b/scripts/warm-reboot
@@ -1,3 +1,4 @@
 #!/bin/bash
-exec reboot now
+import redis
+exec reboot now
"""
        
        patch = PatchSet(demo_diff.splitlines(keepends=True))
        engine = RuleEngine()
        comments = engine.analyze_patchset(patch)
        
        print(f"Self-test: Found {len(comments)} review comments")
        for comment in comments:
            print(f"  - {comment.severity}: {comment.message}")
            
        return len(comments) > 0
        
    except ImportError:
        print("Self-test skipped: unidiff not available")
        return True


if __name__ == "__main__":
    self_test()
