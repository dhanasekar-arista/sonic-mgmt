"""
=============================================================================
Module: layer1
File: test_fec_error.py
=============================================================================

Description:
    This test validates Forward Error Correction (FEC) statistics and counters
    on SONiC devices. It verifies that FEC counters are properly reported,
    formatted correctly, and that no uncorrectable FEC errors are present on
    operational interfaces with supported high-speed configurations.

Test Intent:
    - test_verify_fec_stats_counters: Validates FEC statistics counters for
      interfaces operating at supported speeds (50G-1600G). Checks that FEC
      correctable, uncorrectable, and symbol error counters are valid integers.
      Ensures no uncorrectable FEC errors exist. Validates FEC BER (Bit Error
      Rate) fields, observed FLR (Frame Loss Ratio), and predicted FLR values
      are properly formatted. Verifies logical consistency between FEC counters
      (correctable errors should not exceed symbol errors).

Topology:
    any topology

Fixtures Used:
    - duthosts: Provides list of DUT hosts for testing
    - enum_rand_one_per_hwsku_frontend_hostname: Selects one random frontend
      DUT per hardware SKU to ensure diverse platform testing

Dependencies:
    - tests.common.platform.interface_utils: Provides get_fec_eligible_interfaces
      to identify interfaces suitable for FEC testing

Notes:
    - Supported platforms: mlnx_msn, 8101_32fh, 8111_32eh, arista, x86_64-nvidia,
      x86_64-88_lc0_36fh_m-r0, x86_64-nexthop_4010-r0, marvell
    - Supported speeds: 50G, 100G, 200G, 400G, 800G, 1600G
    - Test skips if no FEC-eligible interfaces are found
    - Pre-FEC and Post-FEC BER fields may not be available on all platforms
    - FLR(O) observed and FLR(P) predicted fields are optional
    - Predicted FLR format: "0" or scientific notation with accuracy percentage
      (e.g., "7.81e-10 (89%)")
    - Disables log analyzer to prevent interference with error counter validation
=============================================================================
"""
import logging
import pytest
import re

from tests.common.platform.interface_utils import clear_interface_counters_and_wait, get_fec_eligible_interfaces

pytestmark = [
    pytest.mark.disable_loganalyzer,  # disable automatic loganalyzer
    pytest.mark.topology('any')
]

SUPPORTED_PLATFORMS = [
    "mlnx_msn",
    "8101_32fh",
    "8111_32eh",
    "arista",
    "x86_64-nvidia",
    "x86_64-88_lc0_36fh_m-r0",
    "x86_64-nexthop_4010-r0",
    "marvell"
]

SUPPORTED_SPEEDS = [
    "50G", "100G", "200G", "400G", "800G", "1600G"
]


def test_verify_fec_stats_counters(duthosts, enum_rand_one_per_hwsku_frontend_hostname):
    """
    @Summary: Verify the FEC stats counters are valid
    Also, check for any uncorrectable FEC errors
    """
    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]

    # Get operationally up and interfaces with supported speeds
    interfaces = get_fec_eligible_interfaces(duthost, SUPPORTED_SPEEDS)

    if not interfaces:
        pytest.skip("Skipping this test as there is no fec eligible interface")

    clear_interface_counters_and_wait(duthost)

    logging.info("Get output of 'show interfaces counters fec-stats'")
    intf_status = duthost.show_and_parse("show interfaces counters fec-stats")

    def skip_ber_counters_test(intf_status: dict) -> bool:
        """
        Check whether the BER fields (Pre-FEC and Post-FEC BER)
        exists in the "show interfaces counters fec-stats"
        CLI output
        """
        if intf_status.get('fec_pre_ber') is None or intf_status.get('fec_post_ber') is None:
            pytest.skip("Pre-FEC and Post-FEC BER fields missing on interface. intf_status: {}".format(intf_status))
            return True
        return False

    def skip_fec_flr_counters_test(intf_status: dict) -> bool:
        """
        Check whether the Observed FLR field FLR(O) exists
        in the "show interfaces counters fec-stats"
        CLI output
        """
        if intf_status.get('flr(o)') is None:
            pytest.skip("FLR(O) field is missing on interface. intf_status: {}".format(intf_status))
            return True
        return False

    def skip_predicted_flr_counters_test(intf_status: dict) -> bool:
        """
        Check whether the Predicted FLR field FLR(P) exists
        in the "show interfaces counters fec-stats"
        CLI output
        """
        if intf_status.get('flr(p) (accuracy)') is None:
            pytest.skip("FLR(P) field is missing on interface. intf_status: {}".format(intf_status))
            return True
        return False

    def validate_predicted_flr(value_string) -> bool:
        """
        Validate predicted flr string is in the correct
        format when not N/A.
        Expected format :
            * 0
            * 7.81e-10 (89%)
        """
        # Pattern for just "0"
        if value_string == "0":
            return True

        # Pattern for scientific notation with required accuracy percentage
        # e.g., "7.81e-10 (89%)"
        pattern = r'^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)\s+\(\d+%\)$'
        if re.match(pattern, value_string):
            return True

        raise ValueError(f"Invalid predicted FLR format: {value_string}")

    for intf in intf_status:
        intf_name = intf['iface']
        speed = duthost.get_speed(intf_name)
        # Speed is a empty string if the port isn't up
        if speed == '':
            continue
        # Convert the speed to gbps format
        speed_gbps = f"{int(speed) // 1000}G"
        if speed_gbps not in SUPPORTED_SPEEDS:
            continue

        # Removes commas from "show interfaces counters fec-stats" (i.e. 12,354 --> 12354) to allow int conversion
        fec_corr = intf.get('fec_corr', '').replace(',', '').lower()
        fec_uncorr = intf.get('fec_uncorr', '').replace(',', '').lower()
        fec_symbol_err = intf.get('fec_symbol_err', '').replace(',', '').lower()
        # Check if fec_corr, fec_uncorr, and fec_symbol_err are valid integers
        try:
            fec_corr_int = int(fec_corr)
            fec_uncorr_int = int(fec_uncorr)
            fec_symbol_err_int = int(fec_symbol_err)
        except ValueError:
            pytest.fail("FEC stat counters are not valid integers for interface {}, \
                        fec_corr: {} fec_uncorr: {} fec_symbol_err: {}"
                        .format(intf_name, fec_corr, fec_uncorr, fec_symbol_err))

        # Check for non-zero FEC uncorrectable errors
        if fec_uncorr_int > 0:
            pytest.fail("FEC uncorrectable errors are non-zero for interface {}: {}"
                        .format(intf_name, fec_uncorr_int))

        # FEC correctable codeword errors should always be less than actual FEC symbol errors, check it
        if fec_corr_int > 0 and fec_corr_int > fec_symbol_err_int:
            pytest.fail("FEC symbol errors:{} are higher than FEC correctable errors:{} for interface {}"
                        .format(fec_symbol_err_int, fec_corr_int, intf_name))

        # Test for observed flr
        if not skip_fec_flr_counters_test(intf):
            fec_flr = intf.get('flr(o)', '').lower()
            try:
                if fec_flr != "n/a":
                    float(fec_flr)
            except ValueError:
                pytest.fail("fec_flr is not a valid float for interface {}, \
                            fec_flr: {}".format(intf_name, fec_flr))

        # Test for predicted flr
        if not skip_predicted_flr_counters_test(intf):
            fec_flr_predicted = intf.get('flr(p) (accuracy)', '').lower()
            try:
                if fec_flr_predicted != "n/a":
                    validate_predicted_flr(fec_flr_predicted)
            except ValueError:
                pytest.fail("predicted_flr is not a valid float for interface {}, \
                            flr(p): {}".format(intf_name, fec_flr_predicted))
