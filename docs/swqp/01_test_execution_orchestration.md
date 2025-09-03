# Weekly Test Execution Orchestration
**SONiC Weekly Quality Platform - Section 1**

## Overview
The orchestration system manages automated execution of sonic-mgmt test suites across multiple servers and topologies on a weekly schedule.

## Current State
We already have Jenkins jobs for running test suites on testbeds. We need to enhance this with additional jobs:

## Required Jenkins Jobs

### 1. Testbed Sanitization & Deployment Job
- **Purpose**: Sanitize and deploy topology on fixed testbeds
- **Triggers**: Before each test suite execution
- **Functions**:
  - Clean existing testbed configuration
  - Deploy required topology (t0, t1, t2, dualtor, multi-asic)
  - Verify testbed readiness
  - Report deployment status

### 2. Test Suite Execution Job
- **Purpose**: Run sonic-mgmt test suites on prepared testbeds
- **Functions**:
  - Execute test suites using existing run_tests.sh framework
  - Handle test retries for flaky tests
  - Monitor execution progress and timeouts
  - Collect execution metadata

### 3. Results Collection & Storage Job
- **Purpose**: Collect and store test results (including rerun data) in centralized location
- **Functions**:
  - Gather all test artifacts (.xml, .log files)
  - Collect rerun data from retried_tests directory
  - Store results in centralized database
  - Archive artifacts for historical analysis


