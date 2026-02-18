"""
=============================================================================
Module: platform_tests
File: test_sensors.py
=============================================================================

Description:
    Tests hardware sensor readings from lm-sensors. Validates that sensor values
    are within expected ranges per platform SKU and dynamically adjusts checks
    based on installed PSU models.

Test Intent:
    - test_sensors: Verify all lm-sensors readings are within expected ranges per SKU
      with dynamic PSU sensor validation

Topology:
    Any topology

Fixtures Used:
    - duthosts: Multi-DUT host fixture
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hardware SKU
    - sensors_data: Module-scoped fixture loading sensor ranges from YAML

Dependencies:
    - lm-sensors for sensor data collection
    - sku-sensors-data.yml for expected sensor ranges per SKU/platform
    - psu-sensors-data.yml for PSU-specific sensor ranges
    - SensorHelper for dynamic PSU sensor validation
    - mellanox_data for hardware version detection

Notes:
    - Test skips if sensors not supported on platform
    - Expected sensor ranges defined in ../../ansible/group_vars/sonic/sku-sensors-data.yml
    - Dynamic PSU support: removes checks for missing PSUs, adds checks for installed PSUs
    - PSU-specific sensor ranges in psu-sensors-data.yml
    - Validates voltage, current, power, temperature sensors
    - Test supports Mellanox platforms with dynamic PSU detection
    - Sensor values must fall within min/max thresholds
    - JSON and YAML formatters for diagnostic output
    - Hardware version used to select correct sensor data
=============================================================================
"""
import json
import logging
import os
import pytest
import yaml
from tests.common.helpers.assertions import pytest_assert
from tests.common import mellanox_data

from tests.platform_tests.sensors_utils.psu_sensor_utils import SensorHelper

pytestmark = [
    pytest.mark.topology('any')
]

SENSORS_DATA_FILE = "../../ansible/group_vars/sonic/sku-sensors-data.yml"


def to_json(obj):
    return json.dumps(obj, indent=4)


def to_yaml(obj):
    return yaml.dump(obj, indent=4)


@pytest.fixture(scope='module')
def sensors_data():
    """
    Parses SENSORS_DATA_FILE yaml.
    """
    sensors_data_file_full_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), SENSORS_DATA_FILE)
    return yaml.safe_load(open(sensors_data_file_full_path).read())


def update_sensors_checks(duthost, sensors_checks, hardware_version):
    """
    This function will update the update_sensors_checks dynamically according to the sensors of the PSUs installed on
    the dut, specified in psu-sensors-data.yml. In order to do that, we first remove all PSU related sensors from
    sensors_checks variable and then add the correct ones from psu-sensors-data.yml.
    @param duthost: duthost fixture
    @param sensors_checks: the sensors data fetched from sensors-sku-data.yml file
    @param hardware_version: hardware version as retrieved from mellanox_data.get_hardware_version
    """
    sensor_helper = SensorHelper(duthost)
    if sensor_helper.platform_supports_dynamic_psu():
        # Remove sensors of PSUs that aren't installed on the dut
        missing_psu_indexes = sensor_helper.get_missing_psus()
        if missing_psu_indexes:
            sensor_helper.remove_psu_checks(sensors_checks, missing_psu_indexes)

        psu_models_to_replace = sensor_helper.get_psu_index_model_dict()
        # We only replace psus that are covered by psu-sensors-data.yml
        if psu_models_to_replace:
            logging.info(f"Fetching PSU sensors for PSUS: {psu_models_to_replace}\n")
            if sensor_helper.get_uncovered_psus():
                logging.warning(f"Unsupported PSUs (regardless of fan direction) in psu_data.yml: "
                                f"{sensor_helper.get_uncovered_psus()}\n")

            sensor_helper.remove_psu_checks(sensors_checks, set(psu_models_to_replace.keys()))

            sensor_helper.update_psu_sensors(sensors_checks, psu_models_to_replace, hardware_version)
        else:
            logging.warning(f"PSU sensors not covered by psu_data.yml. Unsupported PSUs"
                            f" (regardless of fan direction): {sensor_helper.get_uncovered_psus()}\n")


def test_sensors(duthosts, rand_one_dut_hostname, sensors_data):
    duthost = duthosts[rand_one_dut_hostname]
    # Get platform name
    platform = duthost.facts['platform']
    hardware_version = ""
    if mellanox_data.is_mellanox_device(duthost):
        hardware_version = mellanox_data.get_hardware_version(duthost, platform)
        if hardware_version:
            platform = platform + '-' + hardware_version

    # Prepare check list
    sensors_checks = sensors_data['sensors_checks']

    if platform not in list(sensors_checks.keys()):
        pytest.skip("Skip test due to not support check sensors for current platform({})".format(platform))

    update_sensors_checks(duthost, sensors_checks[platform], hardware_version)
    logging.info("Sensor checks:\n{}".format(to_json(sensors_checks[platform])))

    # Gather sensor facts
    sensors_facts = duthost.sensors_facts(checks=sensors_checks[platform])['ansible_facts']

    logging.info("Sensor facts:\n{}".format(to_json(sensors_facts)))

    # Analyze sensor alarms
    is_sensor_alarm = sensors_facts['sensors']['alarm']
    sensor_alarms = sensors_facts['sensors']['alarms']

    pytest_assert(not is_sensor_alarm, "Sensor alarms:\n{}".format(to_json(sensor_alarms)))

    # Analyze sensor warnings
    is_sensor_warning = sensors_facts['sensors']['warning']
    sensor_warnings = sensors_facts['sensors']['warnings']

    if is_sensor_warning:
        logging.warning("Sensor warnings:\n{}".format(to_json(sensor_warnings)))
