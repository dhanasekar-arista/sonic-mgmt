SONiC Weekly Quality Platform (SWQP)  
Functional Requirements Document – v1.0

0. Scope & Objectives  
• Provide a unified, fully-automated framework that (a) executes sonic-mgmt tests weekly across all supported topologies on multiple test servers, (b) analyses and stores results, (c) identifies regressions & flaky failures, (d) links to existing GitHub issues or files new ones, (e) tracks defects to closure, and (f) exposes dashboards & notifications that keep engineering teams continuously informed of SONiC quality.  
• Initial deployment must support current Arista lab (tst-esx-31/32/60/61/62) and mainline + release/202505 branches.

──────────────────────────────────────────────────────────────────────────────
1. Weekly Test Execution Orchestration
1.1 Scheduler  
 FR-1 A central Jenkins (or GitHub Actions self-hosted runner) job named "sonic-weekly-matrix" SHALL trigger every Sunday 00:30 UTC and on-demand.  
 FR-2 Scheduler SHALL read a YAML matrix (test_matrix.yml) describing:
       • branch (e.g. master, 202505)  
       • topology (t0, t1, t1-64-lag, t2, dualtor, multi-asic)  
       • DUT image URL/hash  
       • server pool (list or label selector)  
 FR-3 Scheduler SHALL allocate runs to available servers based on labels (ASIC-count, PTF-present, HW-SKU) and current health. If insufficient servers are free, remaining jobs SHALL queue until capacity is freed.  
 FR-4 Each run SHALL execute run_tests.sh (see AGENTS.md 8-14) inside sonic-mgmt Docker; DUT image flashing and testbed preparation steps must be included.  
 FR-5 Orchestrator SHALL enforce a maximum wall-time per test suite (configurable, default 6 h) and kill + mark timeout if exceeded.  
 FR-6 For resiliency, any run that fails infrastructure pre-checks (DUT unreachable, container crash) SHALL auto-retry once on an alternate server before being marked "infra-error".

──────────────────────────────────────────────────────────────────────────────
2. Results Collection & Analysis Framework
2.1 Artifact Collection  
 FR-7 Upon test completion each server SHALL archive:  
    • pytest .xml & .log files  
    • syslog, sairedis.rec, config DB snapshot (pre/post)  
    • Ansible playbook logs (if used)  
 FR-8 Artifacts SHALL be rsynced to central storage (/mnt/sonic-weekly/<run-id>/) and retained ≥ 90 days.

2.2 Analysis Engine  
 FR-9 A stateless Python micro-service "swqp-analyzer" (Kubernetes cronjob) SHALL invoke the existing test_script.py plus additional parsers to transform artifacts into a canonical JSON schema (RunReport v2).  
 FR-10 Analyzer SHALL compute per-run metrics: passed, failed, errored, xfail, skipped, success-rate, duration, flake-count.  
 FR-11 For each failed test it SHALL capture: full nodeid, failure phase (setup/call/teardown), traceback digest (first 10 lines), and pointers to log excerpts.  
 FR-12 Analyzer SHALL tag failures as:  
    • PERSISTENT – failed in last N consecutive weeklies (N configurable, default 3)  
    • NEW – failed now but passed last week  
    • FLAKY – failed in run1 but passed in retry / previous run on same commit  
    • INFRA – infrastructure error (labelled per FR-6).  
 FR-13 RunReport JSON SHALL be written to PostgreSQL DB (sonic_quality) via SQLAlchemy.

──────────────────────────────────────────────────────────────────────────────
3. Defect Tracking & Issue Management
3.1 Internal Defect DB  
 FR-14 A Defect entity SHALL include: id, title, severity, category (BGP, QoS, Platform…), current-status, first-seen-date, last-seen-date, owner, linked-github-issue, affected-tests[], evidence-urls[].  
 FR-15 Analyzer SHALL call "defect_resolver" service that:  
  a) hashes (topology + test_name + traceback_digest) to search existing Defect rows;  
  b) if found → update last-seen; attach new RunReport references;  
  c) if not found, proceed to GitHub integration (section 5) and create a new Defect if still unmatched.  
 FR-16 Defects SHALL transition through states: NEW → ASSIGNED → IN-PROGRESS → FIX-PENDING → VERIFIED-FIXED → CLOSED (auto-close after 3 clean weeklies).

──────────────────────────────────────────────────────────────────────────────
4. Reporting & Dashboard Capabilities
4.1 Individual Server Dashboards  
 FR-17 For each server-run, a static HTML report SHALL be generated using sonic_dashboard_compact.html template (mandatory per guideline).  
 FR-18 The HTML SHALL embed data via JSON-in-script tag to avoid server-side rendering.

4.2 Global Dashboard  
 FR-19 swqp-frontend (React or plain JS) SHALL build sonic_global_dashboard.html each cycle. Tabs: Overview, Analysis, Trends, Defects (ref AGENTS.md 128-134).  
 FR-20 Overview tab SHALL show status cards by topology & branch, drill-down links to server dashboards, Success-Rate heatmap, and infra-health status.  
 FR-21 Analysis tab SHALL list all current week failures, grouped by category, with GitHub/Defect links, "persistent/new/flaky" badges.  
 FR-22 Trends tab SHALL visualise 8-week rolling metrics: pass-rate, new failures count, mean duration.  
 FR-23 Defects tab SHALL surface defect list with filters (status, owner, severity) and allow CSV export.  
 FR-24 All dashboards SHALL self-host via python3 -m http.server on port 9000 per server; global dashboard via nginx/port 8080 on central node.

──────────────────────────────────────────────────────────────────────────────
5. Integration with GitHub Issue Tracking
5.1 Auto-Correlation  
 FR-25 github_issue_checker.py SHALL be invoked for each failed test (rate-limited to 500 calls/hr).  
 FR-26 Search scope:  
  • aristanetworks/sonic-qual.msft issues & PRs  
  • sonic-net/sonic-mgmt issues & PRs  
  • optional extra repos list in config.  
 FR-27 Matching algorithm: fuzzy match on test_name, traceback_digest, error-keywords (≥ 0.8 similarity).  
 FR-28 If match found, defect_resolver SHALL store GitHub issue number in Defect.linked_github_issue.  
 FR-29 If no match and category != INFRA, system SHALL open a new GitHub issue in sonic-qual.msft via PAT with templated body (includes log links) and store link.  
 FR-30 Any state change in GitHub issue (closed, owner-change) SHALL sync back to Defect table via hourly job.

──────────────────────────────────────────────────────────────────────────────
6. Automated Failure Analysis & Categorization
 FR-31 Analyzer SHALL apply heuristic rules:  
  • "AssertionError: BGP neighbor state …" → Category=BGP  
  • "queue length mismatch" → Category=QoS  
  • "FileNotFoundError: /etc/sonic" → Category=Platform  
  Rules configurable via YAML so SMEs can update without code change.  
 FR-32 System SHALL compute flakiness score = (fails / total runs last N weeks); tests with 0 < score < 1 SHALL gain FLAKY label and appear in "Flaky Tests" widget.

──────────────────────────────────────────────────────────────────────────────
7. Regression Detection & Trending
 FR-33 Each Thursday 02:00 UTC a "trend-builder" job SHALL query DB, build week-to-week comparison, and flag:  
  • New Failures – tests passing last week but failing now  
  • Fixed Failures – tests failing last week but passing now  
  • Top Regressed Areas – categories with biggest drop in pass-rate (Δ > 10 %).  
 FR-34 Trend data SHALL feed Trends tab and be exported as CSV for offline BI tools.  
 FR-35 Severe regression (overall pass-rate drop > 15 % or ANY t2 infra fail) SHALL trigger an immediate "RED-ALERT" notification (see section 8).

──────────────────────────────────────────────────────────────────────────────
8. Stakeholder Notification System
8.1 Channels  
 FR-36 Email (smtp-relay), Slack (#sonic-quality), optional MS Teams webhook.  
8.2 Rules  
 FR-37 Summary email EACH Monday 08:00 local time to sonic-eng-all@, containing: overall stats, new failures table, link to dashboard.  
 FR-38 Per-Defect assignment email on creation or ownership change (using templates in AGENTS.md 230-234).  
 FR-39 Escalation reminder after 7 days of no activity on HIGH severity defects.  
 FR-40 RED-ALERT message (FR-35) to Slack within 10 min of detection.

──────────────────────────────────────────────────────────────────────────────
9. Non-Functional Requirements
NF-1 Scalability: framework must support ≥ 15 concurrent servers and 4× topology growth without redesign.  
NF-2 Reliability: All critical services deployed in Kubernetes with 2 replicas min; data stored on HA PostgreSQL + S3/NFS with daily backups.  
NF-3 Security: no hard-coded IPs; credentials stored in Vault; PAT scopes limited to repo:issues.  
NF-4 Performance: Analysis of one full server run (≈ 2000 tests) shall complete < 15 min.  
NF-5 Maintainability: All configs (matrix, categorization rules, email lists) in Git; CI linting & unit-tests for analyzer & dashboard code.  
NF-6 Auditability: every defect and GitHub action logged with user/time; dashboard shows provenance of data.

──────────────────────────────────────────────────────────────────────────────
10. Open Items / Future Enhancements  
• VS/KVM virtual testbed runs for pre-commit PR validation.  
• Historical artifact pruning policy & cold-storage.  
• ML-based root-cause clustering to complement rule-based categorization.  
• REST API for external consumers (e.g., product-quality portals).  

End of document.
