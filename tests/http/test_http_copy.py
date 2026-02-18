"""
=============================================================================
Module: http
File: test_http_copy.py
=============================================================================

Description:
    This test module validates the HTTP file transfer capability on SONiC
    devices. It verifies that files can be successfully downloaded from an
    HTTP server to the DUT using curl, ensuring file integrity through MD5
    checksum validation.

Test Intent:
    - test_http_copy: Verifies that the DUT can successfully download files
      from an HTTP server using curl, validates file integrity by comparing
      MD5 checksums of the original and downloaded files, and ensures proper
      HTTP server startup and shutdown on PTF

Topology:
    - any, t1-multi-asic: Works with any topology including multi-asic setups

Fixtures Used:
    - setup_teardown: Autouse fixture that copies HTTP server scripts to PTF,
      creates a temporary test file, and cleans up files after test completion
    - duthosts: Collection of DUT hosts in the testbed
    - rand_one_dut_hostname: Randomly selects one DUT for testing
    - ptfhost: PTF host used to run HTTP server for file transfers

Dependencies:
    - http/start_http_server.py: Python script to start HTTP server on PTF
    - http/stop_http_server.py: Python script to stop HTTP server on PTF
    - tests.common.helpers.assertions: Test assertion utilities

Notes:
    - Test runs only on virtual switch (vs) device types
    - Log analyzer is disabled for this test
    - Uses port 8080 for HTTP server
    - Generates 1MB random binary file for transfer testing
    - Validates server startup/shutdown with retry logic (10 attempts)
    - File integrity verified using MD5 checksum comparison
    - Temporary files are automatically cleaned up after test
=============================================================================
"""
import os
import pytest
import time
import tempfile
from tests.common.helpers.assertions import pytest_assert

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology("any", "t1-multi-asic"),
    pytest.mark.device_type("vs"),
]

SONIC_SSH_PORT = 22
SONIC_SSH_REGEX = "OpenSSH_[\\w\\.]+ Debian"
HTTP_PORT = "8080"
TEST_FILE_NAME = ""

local_start_server_filename = "http/start_http_server.py"
ptf_start_server_filename = "/tmp/start_http_server.py"
local_stop_server_filename = "http/stop_http_server.py"
ptf_stop_server_filename = "/tmp/stop_http_server.py"


@pytest.fixture(autouse=True)
def setup_teardown(ptfhost):
    global TEST_FILE_NAME

    # Copies http server files to ptf
    ptfhost.copy(src=local_start_server_filename, dest=ptf_start_server_filename)
    ptfhost.copy(src=local_stop_server_filename, dest=ptf_stop_server_filename)

    with tempfile.NamedTemporaryFile(prefix="http_copy_test_file", suffix=".bin") as test_file:
        TEST_FILE_NAME = os.path.basename(test_file.name)

        # this 'yield' is inside the scope of the with-statment so that the temporary binary will be in scope for the
        # test but will be automatically deleted when the test is done
        yield

        # Delete files off ptf and ensure that files were removed
        files_to_remove = [ptf_start_server_filename, ptf_stop_server_filename]

        for file in files_to_remove:
            ptfhost.file(path=file, state="absent")


def test_http_copy(duthosts, rand_one_dut_hostname, ptfhost):
    """Test that HTTP (copy) can be used to download objects to the DUT"""

    duthost = duthosts[rand_one_dut_hostname]
    ptf_ip = ptfhost.mgmt_ip

    # Starts the http server on the ptf
    ptfhost.command(f"python {ptf_start_server_filename}", module_async=True)

    # Validate HTTP Server has started
    started = False
    tries = 0
    while not started and tries < 10:
        if os.system("curl {}:8080".format(ptf_ip)) == 0:
            started = True
        tries += 1
        time.sleep(1)

    pytest_assert(started, "HTTP Server could not be started")

    # Generate the file from /dev/urandom
    ptfhost.command(("dd if=/dev/urandom of=./{} count=1 bs=1000000 iflag=fullblock".format(TEST_FILE_NAME)))

    # Ensure that file was downloaded
    file_stat = ptfhost.stat(path="./{}".format(TEST_FILE_NAME))

    pytest_assert(file_stat["stat"]["exists"], "Test file was not found on DUT after attempted http get")

    # Generate MD5 checksum to compare with the sent file
    output = ptfhost.command("md5sum ./{}".format(TEST_FILE_NAME))["stdout"]
    orig_checksum = output.split()[0]

    # Have DUT request file from http server
    duthost.command("curl -O {}:{}/{}".format(ptf_ip, HTTP_PORT, TEST_FILE_NAME))

    # Validate file was received
    file_stat = duthost.stat(path="./{}".format(TEST_FILE_NAME))

    pytest_assert(file_stat["stat"]["exists"], "Test file was not found on DUT after attempted http get")

    # Get MD5 checksum of received file
    output = duthost.command("md5sum ./{}".format(TEST_FILE_NAME))["stdout"]
    new_checksum = output.split()[0]

    # Confirm that the received file is identical to the original file
    pytest_assert(orig_checksum == new_checksum, "Original file differs from file sent to the DUT")

    # Stops http server
    ptfhost.command(f"python {ptf_stop_server_filename}")

    # Ensure that HTTP server was closed
    started = True
    tries = 0
    while started and tries < 10:
        if os.system("curl {}:8080".format(ptf_ip)) != 0:
            started = False
        tries += 1
        time.sleep(1)

    pytest_assert(not started, "HTTP Server could not be stopped.")
