"""
=============================================================================
Module: upgrade_path
File: test_upgrade_gnoi.py
=============================================================================

Description:
    This test file validates SONiC software upgrade using the gNOI (gRPC Network
    Operations Interface) protocol instead of traditional CLI-based upgrade methods.
    It tests the gNOI OS Install and Activate RPCs to transfer images to the DUT
    and perform warm or cold upgrades via standardized gRPC interfaces.

Test Intent:
    - test_upgrade_via_gnoi: Validates gNOI-based software upgrade by setting up
      base image, transferring target image to DUT via gNOI TransferToRemote RPC,
      installing the image via gNOI OS Install RPC, activating the new image with
      specified upgrade type (warm/cold) via gNOI OS Activate RPC, verifying the
      upgrade completes successfully, and checking the new version is active via
      'show version' command.

Topology:
    any (supports all topology types)

Fixtures Used:
    - localhost: Local host for image operations
    - duthosts: All DUT hosts in testbed
    - ptfhost: PTF host for gNOI client operations
    - rand_one_dut_hostname: Randomly selected DUT for testing
    - nbrhosts: Neighbor hosts for connectivity verification
    - fanouthosts: Fanout hosts for topology control
    - tbinfo: Testbed information
    - request: Pytest request object for accessing test configuration
    - gnoi_upgrade_path_lists: Provides upgrade configuration (base/target images,
      version, upgrade type)
    - ptf_gnoi: gNOI client fixture for executing gNOI RPCs
    - setup_gnoi_tls_server: Sets up TLS certificates for secure gNOI communication

Dependencies:
    - pytest: Test framework
    - tests.common.fixtures.grpc_fixtures: gRPC/gNOI fixture setup
    - tests.upgrade_path.test_upgrade_path: Shared upgrade test utilities
    - tests.common.helpers.upgrade_helpers: gNOI upgrade implementation

Notes:
    - Test is marked to disable log analyzer
    - Requires TLS server setup for secure gNOI communication
    - Only tested on 'vs' device type currently
    - Upgrade types supported: warm, cold
    - Image transfer protocol: HTTP (via TransferToRemote)
    - Target image path on DUT: /var/tmp/sonic_image
    - Image cleanup: removes existing image at path before transfer
    - gNOI RPCs used:
      - gnoi.file.TransferToRemote: Transfer image file to DUT
      - gnoi.os.Install: Install the transferred image
      - gnoi.os.Activate: Activate image with reboot
    - Verifies version using 'show version' command post-upgrade
    - Uses GnoiUpgradeConfig dataclass for configuration
    - Supports target version specification for validation
    - allow_fail parameter set to False (no failure injection)
    - Upgrade process follows gNOI OS management specification
    - Provides standardized, vendor-neutral upgrade interface
=============================================================================
"""
import logging
import pytest

from tests.common.fixtures.grpc_fixtures import gnmi_tls  # noqa: F401
from tests.upgrade_path.test_upgrade_path import setup_upgrade_test
from tests.common.helpers.upgrade_helpers import perform_gnoi_upgrade, GnoiUpgradeConfig

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.disable_loganalyzer,
]


@pytest.fixture(scope="module")
def gnoi_upgrade_path_lists(request):
    upgrade_type = request.config.getoption("upgrade_type")          # "warm" / "cold"
    from_image = request.config.getoption("base_image_list")
    to_image = request.config.getoption("target_image_list")
    to_version = request.config.getoption("target_version")

    dut_image_path = "/var/tmp/sonic_image"

    return (upgrade_type, from_image, to_image, to_version, dut_image_path)


@pytest.mark.device_type("vs")
def test_upgrade_via_gnoi(
    localhost, duthosts, ptfhost, rand_one_dut_hostname,
    nbrhosts, fanouthosts, tbinfo, request,
    gnoi_upgrade_path_lists, gnmi_tls  # noqa: F811
):
    duthost = duthosts[rand_one_dut_hostname]

    (upgrade_type, from_image, to_image, to_version, dut_image_path) = gnoi_upgrade_path_lists

    logger.info("Test gNOI upgrade path from %s to %s", from_image, to_image)

    cur = duthost.shell("show version", module_ignore_errors=False)["stdout"]
    logger.info("Pre-upgrade show version:\n%s", cur)

    duthost.shell(f"rm -f {dut_image_path}", module_ignore_errors=True)

    assert to_image, "target_image_list must be set (used as to_image for gNOI TransferToRemote)"

    cfg = GnoiUpgradeConfig(
        to_image=to_image,
        dut_image_path=dut_image_path,
        upgrade_type=upgrade_type,
        protocol="HTTP",
        allow_fail=False,
        to_version=to_version,
    )

    def upgrade_path_preboot_setup():
        setup_upgrade_test(duthost, localhost, from_image, to_image, tbinfo,
                           upgrade_type)

    perform_gnoi_upgrade(
        ptf_gnoi=gnmi_tls.gnoi,
        duthost=duthost,
        tbinfo=tbinfo,
        cfg=cfg,
        cold_reboot_setup=upgrade_path_preboot_setup,
    )
