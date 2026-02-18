"""
=============================================================================
Module: snmp
File: test_snmp_psu.py
=============================================================================

Description:
    This test module validates PSU (Power Supply Unit) monitoring via SNMP on
    SONiC switches. It verifies PSU count accuracy and operational status reporting
    through SNMP by comparing SNMP MIB data with psuutil commands and Redis STATE_DB
    PSU information including presence and status fields.

Test Intent:
    - test_snmp_numpsu: Validates PSU count reported via SNMP matches the number
      returned by psuutil numpsus command on supervisor nodes
    - test_snmp_psu_status: Verifies PSU operational status in SNMP MIB correctly
      reflects actual PSU state from Redis STATE_DB - OK (2) when present and
      functioning, FUNCTIONING_FAIL (7) when present but not functioning,
      MODULE_MISSING (8) when not present

Topology:
    - Supported: any topology
    - Requires supervisor node with PSU information
    - KVM testbeds skipped (no PSU hardware)

Fixtures Used:
    - duthosts: All DUT hosts in testbed
    - enum_supervisor_dut_hostname: Supervisor node selection for PSU access
    - localhost: Local connection for SNMP queries
    - creds_all_duts: SNMP community string credentials

Dependencies:
    - tests.common.helpers.snmp_helpers: SNMP fact collection
    - psuutil: PSU utility command for PSU count
    - Redis STATE_DB: PSU_INFO table with presence and status fields
    - natsort: Natural sorting for PSU key ordering

Notes:
    - PSU status values from SNMP MIB: OK=2, FUNCTIONING_FAIL=7, MODULE_MISSING=8
    - KVM testbeds return rc=2 from psuutil (expected, no chassis)
    - Test validates at least one PSU has OK status
    - PSU indices are 1-based in SNMP, 0-based in Redis keys
    - STATE_DB keys sorted naturally to match SNMP index ordering
    - Presence=true + status=true → PSU_STATUS_OK
    - Presence=true + status=false → PSU_STATUS_FUNCTIONING_FAIL
    - Presence=false → PSU_STATUS_MODULE_MISSING
    - Tests skipped on virtual switches (vs ASIC type)
=============================================================================
"""

import pytest
import logging
from tests.common.helpers.assertions import pytest_assert
from tests.common.helpers.snmp_helpers import get_snmp_facts
from natsort import natsorted

PSU_STATUS_OK = 2
PSU_STATUS_FUNCTIONING_FAIL = 7
PSU_STATUS_MODULE_MISSING = 8

pytestmark = [
    pytest.mark.topology('any')
]


@pytest.mark.bsl
def test_snmp_numpsu(duthosts, enum_supervisor_dut_hostname, localhost, creds_all_duts):
    duthost = duthosts[enum_supervisor_dut_hostname]

    hostip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']

    snmp_facts = get_snmp_facts(
        duthost, localhost, host=hostip, version="v2c",
        community=creds_all_duts[duthost.hostname]["snmp_rocommunity"], wait=True)['ansible_facts']
    res = duthost.shell("psuutil numpsus", module_ignore_errors=True)

    # For kvm testbed, we will get the expected return code 2 because of no chassis
    if duthost.facts["asic_type"] == "vs" and res['rc'] == 2:
        logging.info("Get expected return code 2 on kvm testbed.")
        return

    assert int(res['rc']) == 0, "Failed to get number of PSUs"

    output = res["stdout_lines"]
    numpsus = None
    if len(output):
        try:
            numpsus = int(output[-1])
        except (IndexError, ValueError):
            pass
    assert numpsus == len(snmp_facts['snmp_psu']), "PSUs count doesn't match"


@pytest.mark.bsl
def test_snmp_psu_status(duthosts, enum_supervisor_dut_hostname, localhost, creds_all_duts):
    duthost = duthosts[enum_supervisor_dut_hostname]
    hostip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']
    snmp_facts = get_snmp_facts(
        duthost, localhost, host=hostip, version="v2c",
        community=creds_all_duts[duthost.hostname]["snmp_rocommunity"], wait=True)['ansible_facts']

    psus_on = 0
    msg = "Unexpected operstatus results {} != {} for PSU {}"

    # For kvm testbed, there is no snmp psu info
    if duthost.facts["asic_type"] == "vs":
        logging.info("No snmp psu info on kvm testbed.")
        return

    psu_keys = natsorted(redis_get_keys(duthost, 'STATE_DB', 'PSU_INFO|*'))
    for psu_indx, operstatus in snmp_facts['snmp_psu'].items():
        get_presence = duthost.shell(
            "redis-cli -n 6 hget '{}' presence".format(psu_keys[int(psu_indx)-1]))
        get_status = duthost.shell(
            "redis-cli -n 6 hget '{}' status".format(psu_keys[int(psu_indx)-1]))
        status = get_status['stdout'] == 'true'
        presence = get_presence['stdout'] == 'true'

        if presence and status:
            pytest_assert(int(operstatus['operstatus']) == PSU_STATUS_OK,
                          msg.format(operstatus['operstatus'], PSU_STATUS_OK, psu_indx))
            psus_on += 1
        elif presence and not status:
            pytest_assert(int(operstatus['operstatus']) == PSU_STATUS_FUNCTIONING_FAIL,
                          msg.format(operstatus['operstatus'], PSU_STATUS_FUNCTIONING_FAIL, psu_indx))
        elif not presence:
            pytest_assert(int(operstatus['operstatus']) == PSU_STATUS_MODULE_MISSING,
                          msg.format(operstatus['operstatus'], PSU_STATUS_MODULE_MISSING, psu_indx))

    pytest_assert(
        psus_on >= 1, "At least one PSU should be with operstatus OK")


def redis_get_keys(duthost, db_id, pattern):
    """
    Get all keys for a given pattern in given redis database
    :param duthost: DUT host object
    :param db_id: ID of redis database
    :param pattern: Redis key pattern
    :return: A list of key name in string
    """
    cmd = 'sonic-db-cli {} KEYS \"{}\"'.format(db_id, pattern)
    logging.debug('Getting keys from redis by command: {}'.format(cmd))
    output = duthost.shell(cmd)
    content = output['stdout'].strip()
    return content.split('\n') if content else None
