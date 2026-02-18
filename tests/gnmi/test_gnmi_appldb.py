"""
=============================================================================
Module: gnmi
File: test_gnmi_appldb.py
=============================================================================

Description:
    Tests gNMI operations on APPL_DB in SONiC. Validates native write operations
    for DASH_VNET_TABLE entries including add, update, and delete operations.

Test Intent:
    - test_gnmi_appldb_01: Tests DASH_VNET_TABLE operations via gNMI:
      1. Adds VNET entry with VNI and GUID
      2. Validates entry via gnmi_get
      3. Removes VNET entry
      4. Validates removal

Topology:
    Supports any topology

Fixtures Used:
    - duthosts: DUT host objects
    - rand_one_dut_hostname: Randomly selected DUT
    - ptfhost: PTF host for gNMI client operations

Dependencies:
    - .helper: gnmi_set, gnmi_get for gNMI operations

Notes:
    - Log analyzer disabled for these tests
    - Uses APPL_DB DASH_VNET_TABLE path
    - Tests both _DASH_VNET_TABLE and DASH_VNET_TABLE paths for compatibility
    - VNI value: "1000", GUID: "559c6ce8-26ab-4193-b946-ccc6e8f930b2"
=============================================================================
"""
import logging
import pytest

from .helper import gnmi_set, gnmi_get

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer,
    pytest.mark.usefixtures("setup_gnmi_ntp_client_server", "setup_gnmi_server",
                            "setup_gnmi_rotated_server", "check_dut_timestamp")
]


def test_gnmi_appldb_01(duthosts, rand_one_dut_hostname, ptfhost):
    '''
    Verify GNMI native write with ApplDB
    Update DASH_VNET_TABLE
    '''
    duthost = duthosts[rand_one_dut_hostname]
    file_name = "vnet.txt"
    text = "{\"Vnet1\": {\"vni\": \"1000\", \"guid\": \"559c6ce8-26ab-4193-b946-ccc6e8f930b2\"}}"
    with open(file_name, 'w') as file:
        file.write(text)
    ptfhost.copy(src=file_name, dest='/root')
    # Add DASH_VNET_TABLE
    update_list = ["/sonic-db:APPL_DB/localhost/DASH_VNET_TABLE:@/root/%s" % (file_name)]
    gnmi_set(duthost, ptfhost, [], update_list, [])
    # Check gnmi_get result
    path_list1 = ["/sonic-db:APPL_DB/localhost/DASH_VNET_TABLE/Vnet1/vni"]
    path_list2 = ["/sonic-db:APPL_DB/localhost/_DASH_VNET_TABLE/Vnet1/vni"]
    output = None
    try:
        msg_list1 = gnmi_get(duthost, ptfhost, path_list1)
    except Exception as e:
        logger.info("Failed to read path1: " + str(e))
    else:
        output = msg_list1[0]
    try:
        msg_list2 = gnmi_get(duthost, ptfhost, path_list2)
    except Exception as e:
        logger.info("Failed to read path2: " + str(e))
    else:
        output = msg_list2[0]
    assert output == "\"1000\"", "Unexpected output: '{}'".format(output)

    # Remove DASH_VNET_TABLE
    delete_list = ["/sonic-db:APPL_DB/localhost/DASH_VNET_TABLE/Vnet1"]
    gnmi_set(duthost, ptfhost, delete_list, [], [])
    # Check gnmi_get result
    path_list1 = ["/sonic-db:APPL_DB/localhost/DASH_VNET_TABLE/Vnet1/vni"]
    path_list2 = ["/sonic-db:APPL_DB/localhost/_DASH_VNET_TABLE/Vnet1/vni"]
    try:
        msg_list1 = gnmi_get(duthost, ptfhost, path_list1)
    except Exception as e:
        logger.info("Failed to read path1: " + str(e))
    else:
        pytest.fail("Remove DASH_VNET_TABLE failed: " + msg_list1[0])
    try:
        msg_list2 = gnmi_get(duthost, ptfhost, path_list2)
    except Exception as e:
        logger.info("Failed to read path2: " + str(e))
    else:
        pytest.fail("Remove DASH_VNET_TABLE failed: " + msg_list2[0])
