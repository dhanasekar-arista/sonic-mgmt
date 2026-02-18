"""
=============================================================================
Module: transceiver
File: test_transceiver_info_cli.py
=============================================================================

Description:
    This test file validates the "show interfaces transceiver info" CLI command
    output by parsing the EEPROM data and comparing it against the transceiver
    inventory collected during test setup. It ensures that transceiver details
    (vendor name, part number, serial number, firmware versions, etc.) are
    correctly displayed and match the actual hardware inventory.

Test Intent:
    - test_check_show_int_transceiver_info: Validates the "show interfaces transceiver
      info" CLI command by executing the command, parsing the EEPROM output for all
      connected transceivers, and verifying that each field (Vendor Date Code, Vendor
      OUI, Vendor Rev, Vendor SN, Vendor PN, Active Firmware, Inactive Firmware,
      CMIS Rev, Vendor Name) matches the corresponding values in the transceiver
      inventory, ensuring accurate CLI reporting of transceiver hardware details.

Topology:
    ptp-256 (physical topology with 256 ports for transceiver testing)

Fixtures Used:
    - Inherits from TransceiverTestBase which provides:
      - duthost: DUT host object for executing commands
      - dev_conn: Dictionary of connected transceiver interfaces
      - dev_transceiver_details: Transceiver inventory from hardware
      - lport_to_pport_mapping: Logical to physical port mapping

Dependencies:
    - pytest: Test framework
    - tests.transceiver.transceiver_test_base: Base class for transceiver tests
    - tests.transceiver.utils.cli_parser_helper: EEPROM parsing utilities

Notes:
    - CLI command: "show interfaces transceiver info"
    - VS testbed returns error code 2 (ERROR_CHASSIS_LOAD) and is skipped
    - Validated EEPROM fields:
      - Vendor Date Code (YYYY-MM-DD Lot) -> vendor_date
      - Vendor OUI -> vendor_oui
      - Vendor Rev -> vendor_rev
      - Vendor SN -> vendor_sn
      - Vendor PN -> vendor_pn
      - Active Firmware -> active_firmware
      - Inactive Firmware -> inactive_firmware
      - CMIS Rev -> cmis_rev
      - Vendor Name -> vendor_name
    - Uses logical to physical port mapping for validation
    - Parsing logic verifies transceiver inventory collection in conftest.py
    - Test ensures CLI accurately reflects hardware transceiver information
    - Validates all connected interfaces with transceivers
=============================================================================
"""
import logging
import pytest

from tests.transceiver.transceiver_test_base import TransceiverTestBase
from tests.transceiver.utils.cli_parser_helper import parse_eeprom

pytestmark = [
    pytest.mark.topology('ptp-256')
]

CMD_SFP_EEPROM = "show interfaces transceiver info"
ERROR_CHASSIS_LOAD = 2

logger = logging.getLogger(__name__)


class TestTransceiverInfoValidator(TransceiverTestBase):
    """
    @summary: Test class to validate
    transceiver inventory against the parsed EEPROM data.
    """

    EEPROM_EXPECTED_CLI_KEY_TO_TRANSCEIVER_INV_KEY_MAPPING = {
        "Vendor Date Code(YYYY-MM-DD Lot)": "vendor_date",
        "Vendor OUI": "vendor_oui",
        "Vendor Rev": "vendor_rev",
        "Vendor SN": "vendor_sn",
        "Vendor PN": "vendor_pn",
        "Active Firmware": "active_firmware",
        "Inactive Firmware": "inactive_firmware",
        "CMIS Rev": "cmis_rev",
        "Vendor Name": "vendor_name",
    }

    def validate_parsed_eeprom(self, parsed_eeprom):
        for intf in self.dev_conn:
            port_parsed_eeprom = parsed_eeprom[intf]
            port_transceiver_details = self.dev_transceiver_details.get(self.lport_to_pport_mapping[intf], {})
            for cli_key, transceiver_inv_key in self.EEPROM_EXPECTED_CLI_KEY_TO_TRANSCEIVER_INV_KEY_MAPPING.items():
                assert cli_key in port_parsed_eeprom, "{}: {} not present in parsed_eeprom".format(intf, cli_key)
                assert transceiver_inv_key in port_transceiver_details, (
                    "{}: {} not present in transceiver_inventory".format(intf, transceiver_inv_key)
                )
                assert port_parsed_eeprom[cli_key] == port_transceiver_details[transceiver_inv_key], (
                    "{}: {} mismatch for {}: expected {}, got {}".format(
                        intf, cli_key, self.lport_to_pport_mapping[intf],
                        port_transceiver_details[transceiver_inv_key],
                        port_parsed_eeprom[cli_key]
                    )
                )
        logger.info("All transceiver EEPROM contents matched successfully.")

    def test_check_show_int_transceiver_info(self):
        """
        @summary: Check SFP EEPROM using 'show interfaces transceiver eeprom'
        """
        logger.info("Check output of '{}'".format(CMD_SFP_EEPROM))
        sfp_eeprom = self.duthost.command(CMD_SFP_EEPROM, module_ignore_errors=True)

        # For vs testbed, we will get expected Error code `ERROR_CHASSIS_LOAD = 2` here.
        if self.duthost.facts["asic_type"] == "vs" and sfp_eeprom['rc'] == ERROR_CHASSIS_LOAD:
            return
        assert sfp_eeprom['rc'] == 0, "Run command '{}' failed".format(CMD_SFP_EEPROM)

        parsed_eeprom = parse_eeprom(sfp_eeprom["stdout_lines"])

        # Validate the parsed_eeprom against the transceiver inventory
        self.validate_parsed_eeprom(parsed_eeprom)
