"""
=============================================================================
Module: telemetry
File: test_telemetry_cert_rotation.py
=============================================================================

Description:
    This test file validates TLS/SSL certificate rotation functionality for the
    gNMI telemetry service in SONiC. It tests that the telemetry server can handle
    certificate lifecycle operations including starting without certificates,
    certificate deletion, certificate addition, and certificate rotation while
    maintaining service availability and secure connections.

Test Intent:
    - test_telemetry_not_exit: Validates that telemetry server continues running
      when certificates are missing by stopping telemetry, removing certs,
      restarting the service, verifying it starts successfully without certs,
      and confirming it becomes functional after certs are restored.
    - test_telemetry_post_cert_del: Tests certificate deletion impact by making
      a successful gNMI request with valid certs, deleting the certificates,
      attempting a second request that should fail due to missing certs, and
      verifying proper error handling.
    - test_telemetry_post_cert_add: Validates certificate addition by starting
      with no certificates (request fails), rotating/adding new certificates,
      and confirming subsequent gNMI requests succeed with the new certs.
    - test_telemetry_cert_rotate: Tests certificate rotation by making a successful
      request with existing certs, performing certificate rotation with new certs,
      and verifying requests continue to work with the rotated certificates,
      ensuring zero-downtime certificate updates.

Topology:
    any, t1-multi-asic (works with multiple topology types)

Fixtures Used:
    - duthosts: Provides access to all DUT hosts
    - enum_rand_one_per_hwsku_hostname: Selects one DUT per hwsku
    - ptfhost: PTF host for running gNMI client
    - gnxi_path: Path to gNMI client tools on PTF
    - setup_streaming_telemetry: Configures streaming telemetry (parametrized False)
    - localhost: Local host object for operations

Dependencies:
    - pytest: Test framework
    - tests.common.helpers.assertions: For test assertions
    - tests.common.utilities: Provides wait_until and wait_tcp_connection
    - tests.common.helpers.gnmi_utils: gNMI environment utilities
    - telemetry_utils: Certificate rotation and gNMI CLI utilities

Notes:
    - Certificate directory: /etc/sonic/telemetry/
    - Certificates: ca_crt, server_crt, server_key
    - Archive location for backup: /tmp/telemetry_certs.tar.gz
    - Wait timeout for service start: 100 seconds with 10-second intervals
    - Wait timeout for port listening: 120 seconds
    - gNMI method tested: get
    - Subscription mode: POLL (2)
    - Tests use COUNTERS_DB path: COUNTERS/Ethernet0
    - Certificate rotation uses cert-gen.sh script
    - Tests verify both service availability and request success/failure
    - Proper error handling verified when certs are missing
    - Service restart includes systemctl reset-failed for clean state
=============================================================================
"""
import logging
import pytest

from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until, wait_tcp_connection
from tests.common.helpers.gnmi_utils import GNMIEnvironment
from telemetry_utils import generate_client_cli
from telemetry_utils import archive_telemetry_certs, unarchive_telemetry_certs, rotate_telemetry_certs
from telemetry_utils import execute_ptf_gnmi_cli


pytestmark = [
    pytest.mark.topology('any', 't1-multi-asic')
]

logger = logging.getLogger(__name__)

METHOD_GET = "get"
SUBMODE_POLL = 2


@pytest.mark.parametrize('setup_streaming_telemetry', [False], indirect=True)
def test_telemetry_not_exit(duthosts, enum_rand_one_per_hwsku_hostname, setup_streaming_telemetry, localhost):
    """ Test that telemetry server will not exit when certs are missing. We will shutdown telemetry,
    remove certs and verify that telemetry is up and running.
    """
    logger.info("Testing telemetry server will startup without certs")

    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    env = GNMIEnvironment(duthost, GNMIEnvironment.TELEMETRY_MODE)

    # Shutting down telemetry
    duthost.service(name=env.gnmi_container, state="stopped")

    # Remove certs
    archive_telemetry_certs(duthost)

    # Bring back telemetry
    duthost.shell("systemctl reset-failed %s" % (env.gnmi_container), module_ignore_errors=True)
    duthost.service(name=env.gnmi_container, state="restarted")

    # Wait until telemetry is active and running
    pytest_assert(wait_until(100, 10, 0, duthost.is_service_fully_started, env.gnmi_container),
                  "%s not started." % (env.gnmi_container))

    # Restore certs
    unarchive_telemetry_certs(duthost)

    # Wait for telemetry server to listen on port
    dut_ip = duthost.mgmt_ip
    wait_tcp_connection(localhost, dut_ip, env.gnmi_port, timeout_s=60)


@pytest.mark.parametrize('setup_streaming_telemetry', [False], indirect=True)
def test_telemetry_post_cert_del(duthosts, enum_rand_one_per_hwsku_hostname, ptfhost, gnxi_path, localhost,
                                 setup_streaming_telemetry):
    """ Test that telemetry server with certificates will accept requests.
    When certs are deleted, subsequent requests will not work.
    """
    logger.info("Testing telemetry server post cert add")

    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    env = GNMIEnvironment(duthost, GNMIEnvironment.TELEMETRY_MODE)

    # Initial request should pass with certs
    cmd = generate_client_cli(duthost=duthost, gnxi_path=gnxi_path, method=METHOD_GET,
                              target="OTHERS", xpath="proc/uptime")
    pytest_assert(wait_until(30, 5, 0, execute_ptf_gnmi_cli, ptfhost, cmd),
                  "Telemetry server request should complete with certs")

    # Remove certs
    archive_telemetry_certs(duthost)

    # Requests should fail without certs
    ret = ptfhost.shell(cmd, module_ignore_errors=True)['rc']
    assert ret != 0, "Telemetry server request should fail without certs"

    # Restore certs
    unarchive_telemetry_certs(duthost)

    # Wait for telemetry server to listen on port
    dut_ip = duthost.mgmt_ip
    wait_tcp_connection(localhost, dut_ip, env.gnmi_port, timeout_s=60)


@pytest.mark.parametrize('setup_streaming_telemetry', [False], indirect=True)
def test_telemetry_post_cert_add(duthosts, enum_rand_one_per_hwsku_hostname, ptfhost, gnxi_path, localhost,
                                 setup_streaming_telemetry):
    """ Test that telemetry server with no certificates will reject requests.
    When certs are rotated, subsequent requests will work.
    """
    logger.info("Testing telemetry server post cert add")

    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    env = GNMIEnvironment(duthost, GNMIEnvironment.TELEMETRY_MODE)

    # Remove certs
    archive_telemetry_certs(duthost)

    # Initial request should fail without certs
    cmd = generate_client_cli(duthost=duthost, gnxi_path=gnxi_path, method=METHOD_GET,
                              target="OTHERS", xpath="proc/uptime")
    ret = ptfhost.shell(cmd, module_ignore_errors=True)['rc']
    assert ret != 0, "Telemetry server request should fail without certs"

    # Rotate certs
    rotate_telemetry_certs(duthost, localhost)

    # Wait for telemetry server to listen on port
    dut_ip = duthost.mgmt_ip
    wait_tcp_connection(localhost, dut_ip, env.gnmi_port, timeout_s=60)

    # Requests should successfully complete with certs
    pytest_assert(wait_until(30, 5, 0, execute_ptf_gnmi_cli, ptfhost, cmd),
                  "Telemetry server request should complete with certs")


@pytest.mark.parametrize('setup_streaming_telemetry', [False], indirect=True)
def test_telemetry_cert_rotate(duthosts, enum_rand_one_per_hwsku_hostname, ptfhost, gnxi_path, localhost,
                               setup_streaming_telemetry):
    """ Test that telemetry server with certs will serve requests.
    When certs are rotated, subsequent requests will work.
    """
    logger.info("Testing telemetry server cert rotate")

    duthost = duthosts[enum_rand_one_per_hwsku_hostname]
    env = GNMIEnvironment(duthost, GNMIEnvironment.TELEMETRY_MODE)

    # Initial request should complete with certs
    cmd = generate_client_cli(duthost=duthost, gnxi_path=gnxi_path, method=METHOD_GET,
                              target="OTHERS", xpath="proc/uptime")
    pytest_assert(wait_until(30, 5, 0, execute_ptf_gnmi_cli, ptfhost, cmd),
                  "Telemetry server request should complete with certs")

    # Rotate certs
    rotate_telemetry_certs(duthost, localhost)

    # Wait for telemetry server to listen on port
    dut_ip = duthost.mgmt_ip
    wait_tcp_connection(localhost, dut_ip, env.gnmi_port, timeout_s=60)

    # Requests should successfully complete with certs
    pytest_assert(wait_until(30, 5, 0, execute_ptf_gnmi_cli, ptfhost, cmd),
                  "Telemetry server request should complete with certs")
