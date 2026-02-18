"""
=============================================================================
Module: radv
File: test_radv_run.py
=============================================================================

Description:
    Tests radv (Router Advertisement) container behavior with different
    deployment configurations. Validates that radvd service properly starts
    or stops based on deployment_id settings for PortChannel-to-VLAN scenarios.

Test Intent:
    - test_radv_deployment_id: Validates radv container behavior when
      deployment_id is set to '8' (PO2VLAN deployment). Verifies that radvd
      service stops running inside the radv container when deployment_id is
      '8', then confirms normal operation when deployment_id is restored to
      original value.

Topology:
    t0 topology

Fixtures Used:
    - duthost: AnsibleHost instance for DUT operations

Dependencies:
    - tests.common.utilities.wait_until: Polling utility for state checks
    - tests.common.helpers.dut_utils.is_container_running: Container status check

Notes:
    - Marked with @pytest.mark.po2vlan (PortChannel-to-VLAN specific test)
    - PO2VLAN_DEPLOYMENT_ID = '8' (special deployment ID for po2vlan scenario)
    - Gets original deployment_id from CONFIG_DB DEVICE_METADATA|localhost
    - Sets deployment_id to '8' to test po2vlan behavior
    - Regenerates supervisord.conf using sonic-cfggen template
    - Uses systemctl reset-failed before restart to clear failed state
    - Waits up to 10 seconds (polling every 1s) for container to start
    - Verifies radvd service is NOT running when deployment_id='8'
    - Restores original deployment_id after test
    - Template: /usr/share/sonic/templates/docker-router-advertiser.supervisord.conf.j2
    - radvd should not run in po2vlan deployment scenarios
=============================================================================
"""
import pytest
import logging

from tests.common.utilities import wait_until
from tests.common.helpers.dut_utils import is_container_running

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t0')
]

PO2VLAN_DEPLOYMENT_ID = '8'


@pytest.mark.po2vlan
def test_radv_deployment_id(duthost):
    ret = is_container_running(duthost, "radv")
    assert ret is True, "radv container is not running"
    logger.info("Set the deployment id to {} and restart radv".format(PO2VLAN_DEPLOYMENT_ID))
    get_cmd = 'sonic-db-cli CONFIG_DB hget "DEVICE_METADATA|localhost" "deployment_id"'
    set_cmd = 'sonic-db-cli CONFIG_DB hset "DEVICE_METADATA|localhost" "deployment_id" "{}"'
    # Need to generate supervisord.conf
    docker_cmd = 'docker exec radv sonic-cfggen -d -t \
/usr/share/sonic/templates/docker-router-advertiser.supervisord.conf.j2,/etc/supervisor/conf.d/supervisord.conf'
    restart_cmd = 'systemctl reset-failed radv; systemctl restart radv'
    origin_id = duthost.shell(get_cmd)['stdout']
    duthost.shell(set_cmd.format(PO2VLAN_DEPLOYMENT_ID))
    duthost.shell(docker_cmd)
    duthost.shell(restart_cmd)
    assert wait_until(10, 1, 0, is_container_running, duthost, "radv")
    logger.info("Check if radvd process is running")
    ret = duthost.is_service_running("radvd", "radv")
    assert ret is False, "radv service is still running"
    logger.info("Set the deployment id back to {} and restart radv".format(origin_id))
    duthost.shell(set_cmd.format(origin_id))
    duthost.shell(docker_cmd)
    duthost.shell(restart_cmd)
    assert wait_until(10, 1, 0, is_container_running, duthost, "radv")
