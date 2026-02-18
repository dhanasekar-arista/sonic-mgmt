"""
=============================================================================
Module: golden_config_infra
File: test_config_reload_with_rendered_golden_config.py
=============================================================================

Description:
    Tests golden configuration infrastructure for config reload operations.
    Validates rendering golden config from minigraph, applying overrides,
    and ensuring config reload produces expected configuration state.

Test Intent:
    - test_config_reload_with_rendered_golden_config: Validates:
      1. Config reload with minigraph renders golden config correctly
      2. Golden config override is applied properly
      3. Running config matches expected state after reload
      4. Non-user config tables are handled correctly

Topology:
    Supports any topology (single ASIC only)

Fixtures Used:
    - setup_env: Backs up config_db and golden_config, restores after test
    - duthosts: DUT host objects
    - rand_one_dut_hostname: Randomly selected DUT
    - tbinfo: Testbed information

Dependencies:
    - tests.common.config_reload: config_reload, config_reload_minigraph_with_rendered_golden_config_override
    - tests.common.utilities: backup_config, restore_config, get_running_config,
      compare_dicts_ignore_list_order, NON_USER_CONFIG_TABLES, update_pfcwd_default_state

Notes:
    - Log analyzer disabled for these tests
    - Skips on multi-ASIC platforms
    - Golden config: /etc/sonic/golden_config_db.json
    - Config DB: /etc/sonic/config_db.json
    - Backs up both files before test with _before_override suffix
    - Updates pfcwd default state after reload
    - Compares configs ignoring list order differences
=============================================================================
"""
import pytest
import logging
import json
import os

from tests.common.helpers.assertions import pytest_assert
from tests.common.config_reload import config_reload, config_reload_minigraph_with_rendered_golden_config_override
from tests.common.utilities import backup_config, restore_config, get_running_config, \
    compare_dicts_ignore_list_order, NON_USER_CONFIG_TABLES
from tests.common.utilities import update_pfcwd_default_state

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer,
    pytest.mark.disable_memory_utilization,
]

GOLDEN_CONFIG = "/etc/sonic/golden_config_db.json"
GOLDEN_CONFIG_BACKUP = "/etc/sonic/golden_config_db.json_before_override"
CONFIG_DB = "/etc/sonic/config_db.json"
CONFIG_DB_BACKUP = "/etc/sonic/config_db.json_before_override"


def file_exists_on_dut(duthost, filename):
    return duthost.stat(path=filename).get('stat', {}).get('exists', False)


@pytest.fixture(scope="module")
def setup_env(duthosts, rand_one_dut_hostname, tbinfo):
    """
    Setup/teardown
    Args:
        duthost: DUT.
        golden_config_exists_on_dut: Check if golden config exists on DUT.
    """
    duthost = duthosts[rand_one_dut_hostname]
    if duthost.is_multi_asic:
        pytest.skip("Skip test on multi-asic platforms as it is designed for single asic.")

    topo_type = tbinfo["topo"]["type"]
    if topo_type in ["m0", "mx"]:
        original_pfcwd_value = update_pfcwd_default_state(duthost, "/etc/sonic/init_cfg.json", "disable")

    # Backup configDB
    backup_config(duthost, CONFIG_DB, CONFIG_DB_BACKUP)
    if file_exists_on_dut(duthost, GOLDEN_CONFIG):
        backup_config(duthost, GOLDEN_CONFIG, GOLDEN_CONFIG_BACKUP)

    # Reload test env with minigraph
    config_reload(duthost, safe_reload=True, check_intf_up_ports=True)

    yield

    if topo_type in ["m0", "mx"]:
        update_pfcwd_default_state(duthost, "/etc/sonic/init_cfg.json", original_pfcwd_value)

    # Restore configDB after test.
    restore_config(duthost, CONFIG_DB, CONFIG_DB_BACKUP)
    if file_exists_on_dut(duthost, GOLDEN_CONFIG_BACKUP):
        restore_config(duthost, GOLDEN_CONFIG, GOLDEN_CONFIG_BACKUP)
    else:
        duthost.file(path=GOLDEN_CONFIG, state='absent')

    # Restore config before test
    config_reload(duthost)


def config_compare(golden_config, running_config):
    for table in golden_config:
        if table in NON_USER_CONFIG_TABLES:
            continue

        if table == "ACL_TABLE":
            pytest_assert(
                compare_dicts_ignore_list_order(golden_config[table], running_config[table]),
                "ACL_TABLE compare fail!"
            )
        else:
            pytest_assert(
                golden_config[table] == running_config[table],
                "Table compare fail! {}".format(table)
            )


def golden_config_override_with_general_template(duthost):
    # This is to copy and parse the default template: tests/common/templates/golden_config_db.j2
    config_reload_minigraph_with_rendered_golden_config_override(
        duthost, safe_reload=True, check_intf_up_ports=True
    )
    overrided_config = get_running_config(duthost)
    golden_config = json.loads(
        duthost.shell("cat /etc/sonic/golden_config_db.json")['stdout']
    )

    config_compare(golden_config, overrided_config)


def golden_config_override_with_specific_template(duthost):
    # This is to copy and parse the template: tests/golden_config_infra/templates/sample_golden_config_db.j2
    base_dir = os.path.dirname(os.path.realpath(__file__))
    template_dir = os.path.join(base_dir, 'templates')
    golden_config_j2 = os.path.join(template_dir, 'sample_golden_config_db.j2')
    config_reload_minigraph_with_rendered_golden_config_override(
        duthost, safe_reload=True, check_intf_up_ports=True,
        local_golden_config_template=golden_config_j2
    )
    overrided_config = get_running_config(duthost)
    golden_config = json.loads(
        duthost.shell("cat /etc/sonic/golden_config_db.json")['stdout']
    )

    config_compare(golden_config, overrided_config)


def test_rendered_golden_config_override(duthosts, rand_one_dut_hostname, setup_env):
    duthost = duthosts[rand_one_dut_hostname]
    if duthost.is_multi_asic:
        pytest.skip("Skip this test on multi-asic platforms, \
                    since golden config format here is not compatible with multi-asics")

    golden_config_override_with_general_template(duthost)
    golden_config_override_with_specific_template(duthost)
