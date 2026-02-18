"""
Module: tests.database
File: test_db_scripts.py

Description:
    This module contains test cases for validating database utility scripts in SONiC.
    It verifies that database maintenance scripts execute correctly within the database
    container, ensuring proper database cleanup and management operations.

Test Intent:
    - Verify that the flush_unused_database script executes successfully within the
      database container without errors
    - Ensure database maintenance utilities are properly installed and functional
    - Validate database cleanup operations work correctly across supported SONiC releases
      (202012 and later)

Topology:
    - any: Tests can run on any topology (t0, t1, t2, etc.)
    - Device Type: vs (virtual switch) only

Fixtures Used:
    - duthosts: Session-scoped fixture providing DutHosts object containing all DUTs
      in the testbed (defined in tests/conftest.py)
    - rand_one_dut_hostname: Module-scoped fixture that randomly selects one DUT
      hostname from the testbed (defined in tests/conftest.py)

Dependencies:
    - tests.common.utilities.skip_release: Utility to skip test on specific SONiC releases
    - tests.common.helpers.assertions.pytest_assert: Custom assertion helper for better
      error messages
    - Docker: Tests require database container to be running on the DUT
    - flush_unused_database script: Database maintenance script available in SONiC 202012+

Notes:
    - This test is restricted to virtual switch (vs) devices only
    - The flush_unused_database script was introduced in SONiC release 202012
    - Tests are automatically skipped on SONiC releases 201811 and 201911
    - The script runs inside the database Docker container using 'docker exec'
    - Example test execution:
      ./run_tests.sh -n vms-kvm-t0 -d vlab-01 -c database/test_db_scripts.py \
                     -f vtestbed.csv -i veos_vtb

Git History:
    dab77c420 Remove TACACS fixture from none TACACS test cases (#13422)
    07f328770 Enable TACACS on test cases. (#12433)
    49dc10085 Add UT for flush_unused_database (#8032)
"""
import logging
import pytest

from tests.common.utilities import skip_release
from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.device_type('vs')
]


def test_flush_unused_database(duthosts, rand_one_dut_hostname):
    """
    @summary: Test 'flush_unused_database' scripts can run correctly inside database container.
     ./run_tests.sh -n vms-kvm-t0 -d vlab-01 -c database/test_db_scripts.py -f vtestbed.csv -i veos_vtb
    """
    duthost = duthosts[rand_one_dut_hostname]

    # the flush_unused_database exist after 202012 branch
    skip_release(duthost, ["201811", "201911"])

    result = duthost.shell("docker exec -t database flush_unused_database")
    pytest_assert(result["rc"] == 0, "flush_unused_database script failed with {}".format(result["stdout"]))
