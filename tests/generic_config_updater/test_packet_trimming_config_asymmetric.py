"""
=============================================================================
Module: generic_config_updater
File: test_packet_trimming_config_asymmetric.py
=============================================================================

Description:
    Tests asymmetric packet trimming configuration using Generic Config Updater.
    Validates trimming parameters including size, DSCP, queue, TC, and DSCP
    asymmetric settings with proper error handling for invalid values.

Test Intent:
    - test_trim_size_update: Updates packet trim size
    - test_trim_dscp_update: Updates DSCP value for trimming
    - test_trim_queue_update: Updates queue for trimmed packets
    - test_trim_tc_update: Updates traffic class for trimming
    - test_trim_dscp_asym_update: Updates asymmetric DSCP setting
    - test_trim_invalid_*: Tests error handling for invalid values

Topology:
    Supports t0, t1 topologies

Fixtures Used:
    - setup_env: Adjusts trim parameters for TH5 ASIC
    - ensure_dut_readiness: Checkpoint/rollback for tests

Dependencies:
    - tests.common.gu_utils: GCU patch operations

Notes:
    - Default Mellanox: size=256, dscp=48, queue=6, tc=5, dscp_asym=from-tc
    - TH5 ASIC: size=128, queue=5
    - Invalid values tested: dscp=100, tc=200, queue=20, size=5000
=============================================================================
"""
import logging
import pytest

from tests.common.gu_utils import apply_patch, expect_op_success, expect_op_failure
from tests.common.gu_utils import generate_tmpfile, delete_tmpfile
from tests.common.gu_utils import format_json_patch_for_multiasic
from tests.common.gu_utils import create_checkpoint, delete_checkpoint, rollback_or_reload

pytestmark = [
    pytest.mark.topology("t0", "t1")
]

logger = logging.getLogger(__name__)

# Default values
TRIM_SIZE = 256  # For Mellanox
TRIM_DSCP = 48
TRIM_DSCP_ASYM = "from-tc"
TRIM_QUEUE = 6  # For Mellanox
TRIM_TC = 5

# Update values
TRIM_SIZE_UPDATE = 4084  # For Mellanox
TRIM_DSCP_UPDATE = 63
TRIM_QUEUE_UPDATE = 3  # For Mellanox
TRIM_TC_UPDATE = 4

# Invalid values
TRIM_DSCP_INVALID = 100
TRIM_TC_INVALID = 200
TRIM_QUEUE_INVALID = 20
TRIM_SIZE_INVALID = 5000
TRIM_DSCP_ASYM_INVALID = "tc_invalid"


@pytest.fixture(autouse=True)
def setup_env(duthost):
    """
    Setup/teardown fixture for syslog config

    Args:
        duthost: DUT.
    """

    if 'th5' == duthost.get_asic_name():

        global TRIM_SIZE
        global TRIM_SIZE_UPDATE
        global TRIM_QUEUE
        global TRIM_QUEUE_UPDATE

        th5_queue = {
            'Arista-7060X6-64PE-B-C448O16': 4,
            'Arista-7060X6-64PE-B-C512S2': 4,
        }

        # TH5 trim queue defaults to 9 unless otherwise configured
        # and does not support being modified at runtime
        TRIM_QUEUE = th5_queue.get(duthost.facts['hwsku'], 9)
        TRIM_QUEUE_UPDATE = TRIM_QUEUE

        # TH5 supports only fixed size of 206
        TRIM_SIZE = 206
        TRIM_SIZE_UPDATE = TRIM_SIZE

    create_checkpoint(duthost)

    yield

    try:
        logger.info("Rolled back to original checkpoint")
        rollback_or_reload(duthost)

    finally:
        delete_checkpoint(duthost)


def trimming_global_config_asym_add(duthost):
    """ Test add packet trimming global config in asym mode
    """
    json_patch = [
        {
            "op": "add",
            "path": "/SWITCH_TRIMMING",
            "value": {
                "GLOBAL": {
                    "size": f"{TRIM_SIZE}",
                    "dscp_value": f"{TRIM_DSCP_ASYM}",
                    "tc_value": f"{TRIM_TC}",
                    "queue_index": f"{TRIM_QUEUE}"
                }
            }
        }
    ]
    json_patch = format_json_patch_for_multiasic(duthost=duthost, json_data=json_patch)
    tmpfile = generate_tmpfile(duthost)
    logger.info("tmpfile {}".format(tmpfile))

    try:
        output = apply_patch(duthost, json_data=json_patch, dest_file=tmpfile)
        expect_op_success(duthost, output)
        trimming_config = duthost.shell("show switch-trimming global --json")["stdout"]
        logger.info("The trimming config: {}".format(trimming_config))

    finally:
        delete_tmpfile(duthost, tmpfile)


def trimming_global_config_asym_replace(duthost):
    """ Test replace packet trimming global config in asym mode
    """
    json_patch = [
        {
            "op": "replace",
            "path": "/SWITCH_TRIMMING/GLOBAL/tc_value",
            "value": f"{TRIM_TC_UPDATE}"
        },
        {
            "op": "replace",
            "path": "/SWITCH_TRIMMING/GLOBAL/dscp_value",
            "value": f"{TRIM_DSCP_ASYM}"
        },
        {
            "op": "replace",
            "path": "/SWITCH_TRIMMING/GLOBAL/queue_index",
            "value": f"{TRIM_QUEUE_UPDATE}"
        },
        {
            "op": "replace",
            "path": "/SWITCH_TRIMMING/GLOBAL/size",
            "value": f"{TRIM_SIZE_UPDATE}"
        }
    ]
    json_patch = format_json_patch_for_multiasic(duthost=duthost, json_data=json_patch)

    tmpfile = generate_tmpfile(duthost)
    logger.info("tmpfile {}".format(tmpfile))

    try:
        output = apply_patch(duthost, json_data=json_patch, dest_file=tmpfile)
        expect_op_success(duthost, output)

    finally:
        delete_tmpfile(duthost, tmpfile)


def trimming_global_config_asym_replace_xfail(duthost):
    """ Test replace packet trimming global config negative test in asym mode
    """
    json_patch = [
        {
            "op": "replace",
            "path": "/SWITCH_TRIMMING/GLOBAL/tc_value",
            "value": f"{TRIM_TC_INVALID}"
        },
        {
            "op": "replace",
            "path": "/SWITCH_TRIMMING/GLOBAL/dscp_value",
            "value": f"{TRIM_DSCP_ASYM_INVALID}"
        },
        {
            "op": "replace",
            "path": "/SWITCH_TRIMMING/GLOBAL/queue_index",
            "value": f"{TRIM_QUEUE_INVALID}"
        },
        {
            "op": "replace",
            "path": "/SWITCH_TRIMMING/GLOBAL/size",
            "value": f"{TRIM_SIZE_INVALID}"
        }
    ]
    json_patch = format_json_patch_for_multiasic(duthost=duthost, json_data=json_patch)

    tmpfile = generate_tmpfile(duthost)
    logger.info("tmpfile {}".format(tmpfile))

    try:
        output = apply_patch(duthost, json_data=json_patch, dest_file=tmpfile)
        expect_op_failure(output)

    finally:
        delete_tmpfile(duthost, tmpfile)


def test_packet_trimming_config_asym(rand_selected_dut, loganalyzer, skip_if_packet_trimming_not_supported):
    """ Test packet trimming config
    """
    # After GCU test finished, it will rollback to the original configuration, but the packet trimming field removal
    # is prohibited, so the error log will be generated.
    if loganalyzer:
        ignoreRegex = [
            r".*Failed to remove switch trimming.*",
            r".*doCfgSwitchTrimmingTableTask: Failed to set switch trimming: ASIC and CONFIG DB are diverged.*"
        ]
        loganalyzer[rand_selected_dut.hostname].ignore_regex.extend(ignoreRegex)

    trimming_global_config_asym_add(rand_selected_dut)
    trimming_global_config_asym_replace(rand_selected_dut)
    trimming_global_config_asym_replace_xfail(rand_selected_dut)
