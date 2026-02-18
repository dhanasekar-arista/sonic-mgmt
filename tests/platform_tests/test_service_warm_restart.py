"""
=============================================================================
Module: platform_tests
File: test_service_warm_restart.py
=============================================================================

Description:
    Tests warm restart functionality for individual SONiC services. Validates that
    services can be warm-restarted without causing traffic loss or system instability.

Test Intent:
    - test_warm_restart_service: Verify warm restart for built-in services
      (teamd, swss, bgp, etc.) maintains system stability

Topology:
    T0 topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - localhost: Localhost connection
    - ptfhost: PTF host fixture
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hardware SKU
    - get_advanced_reboot: Advanced reboot fixture for warm restart
    - verify_dut_health: Health check after warm restart
    - copy_ptftests_directory: PTF tests directory setup
    - advanceboot_loganalyzer: Log analysis for advanced reboot
    - check_image_version: Module fixture skipping old releases

Dependencies:
    - SPM (SONiC Package Manager) for service listing
    - warm restart configuration
    - get_advanced_reboot for warm restart operations
    - verify_dut_health for health validation

Notes:
    - Test skips releases older than 202205
    - Built-in services from 'spm list' with status 'Built-In'
    - get_ignored_services excludes services from CLI option
    - get_running_services lists currently running Docker containers
    - Validates service warm restarts without traffic loss
    - Loganalyzer disabled (expected logs during service restart)
    - Test uses get_advanced_reboot fixture for controlled restart
=============================================================================
"""
import pytest
import logging

from tests.common.fixtures.advanced_reboot import get_advanced_reboot       # noqa: F401
from tests.common.helpers.assertions import pytest_require
from tests.common.utilities import skip_release
from tests.common.platform.device_utils import verify_dut_health         # noqa: F401
from tests.common.fixtures.ptfhost_utils import copy_ptftests_directory     # noqa: F401
from tests.common.platform.device_utils import advanceboot_loganalyzer  # noqa: F401

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology('t0')
]


@pytest.fixture(autouse=True, scope="module")
def check_image_version(duthost):
    """Skips this test if the SONiC image installed on DUT is older than 202205

    Args:
        duthost: Hostname of DUT.

    Returns:
        None.
    """
    skip_release(duthost, ["201811", "201911", "202012", "202106"])


def get_builtin_services(duthost):
    spm_data = duthost.show_and_parse('spm list')
    return {item['name'] for item in spm_data if item['status'] == 'Built-In'}


def get_running_services(duthost):
    services = duthost.shell(r'docker ps --format \{\{.Names\}\}')['stdout_lines']
    return services


def get_ignored_services(request):
    ignored_services = request.config.getoption("--ignore_service")
    return ignored_services.split(',') if ignored_services else []


class ServiceMatchRules:
    services_warmboot_unsupported = ['database', 'syncd']

    def __init__(self, duthost, request):
        feature_info = duthost.show_and_parse('show feature status')
        self.feature_data = {info['feature']: info for info in feature_info}

        self.ignored_services = get_ignored_services(request)
        self.builtin_services = get_builtin_services(duthost)
        self.running_services = get_running_services(duthost)

    def is_running(self, s):
        return s in self.running_services

    def is_not_ignored(self, s):
        return s not in self.ignored_services

    def is_built_in(self, s):
        return s in self.builtin_services

    def is_feature_enabled(self, s):
        return self.feature_data[s]['state'] not in ['disabled', 'always_disabled']

    def is_warmboot_supported(self, s):
        return s not in ServiceMatchRules.services_warmboot_unsupported


def select_services_to_warmrestart(duthost, request):
    all_services = [feature_data['feature'] for feature_data in duthost.show_and_parse('show feature status')]

    rules = ServiceMatchRules(duthost, request)

    not_running_services = [service for service in all_services if not rules.is_running(service)]
    if not_running_services:
        logging.info('skipping test for not running services: {}'.format(not_running_services))

    all_checks = [
        rules.is_built_in,
        rules.is_warmboot_supported,
        rules.is_not_ignored,
        rules.is_running,
        rules.is_feature_enabled
    ]

    def passes_all_checks(service):
        return all(rule(service) for rule in all_checks)

    return [service for service in all_services if passes_all_checks(service)]


def test_service_warm_restart(request, duthosts, rand_one_dut_hostname,
                              verify_dut_health, get_advanced_reboot,       # noqa: F811
                              advanceboot_loganalyzer,  # noqa: F811
                              capture_interface_counters):
    duthost = duthosts[rand_one_dut_hostname]

    candidate_service_list = select_services_to_warmrestart(duthost, request)
    pytest_require(candidate_service_list, 'Skip service warm restart test because candidate_service_list is empty')

    advancedReboot = get_advanced_reboot(rebootType='service-warm-restart',
                                         service_list=candidate_service_list,
                                         advanceboot_loganalyzer=advanceboot_loganalyzer)
    try:
        advancedReboot.runRebootTestcase()
    finally:
        advancedReboot.disable_service_warmrestart()
