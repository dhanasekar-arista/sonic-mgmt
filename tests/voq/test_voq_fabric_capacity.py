"""
=============================================================================
Module: voq
File: test_voq_fabric_capacity.py
=============================================================================

Description:
    This test validates the fabric capacity monitoring functionality on VOQ
    chassis systems. It verifies that the "show fabric monitor capacity"
    command correctly reports operating fabric links and responds to link
    isolation events.

Test Intent:
    - test_fabric_capacity: Validates fabric capacity monitor by checking
      initial operating link count, manually isolating a fabric link, waiting
      for capacity event trigger, verifying event is reported, then unisolating
      the link and confirming capacity returns to normal.

Topology:
    t2 (VOQ chassis topology)

Fixtures Used:
    - duthosts: Multi-DUT fixture for chassis systems
    - enum_frontend_dut_hostname: Enumerates frontend DUTs (linecards)

Dependencies:
    - tests.common.helpers.assertions: For pytest assertions
    - tests.common.utilities: For wait_until polling

Notes:
    - Test randomly selects an ASIC on multi-ASIC systems
    - Checks "show fabric monitor capacity" output for operating links count
    - Uses "show fabric isolation" to find unisolated links
    - Manually isolates one link to trigger capacity threshold event
    - Polls for up to 600 seconds for capacity event to be reported
    - Always restores link to unisolated state in cleanup
    - Test skips if no unisolated links are available
=============================================================================
"""
import logging
import pytest
import random
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until

logger = logging.getLogger(__name__)

# This test only runs on t2 systems.
pytestmark = [
    pytest.mark.topology('t2')
]

# This test checks the output of the "show fabric monitor capacity" command
# on a linecard. It is designed to run on a modular chassis.


def test_fabric_capacity(duthosts, enum_frontend_dut_hostname):
    """Checks if the fabric capacity monitor works"""

    # get a start state from system
    # by running "show fabric monitor capcity" command
    duthost = duthosts[enum_frontend_dut_hostname]
    asic = 0
    if duthost.is_multi_asic:
        asic = random.randint(0, duthost.num_asics())
    asicName = "asic{}".format(asic)
    logger.info(asicName)

    if duthost.is_multi_asic:
        cmd = "show fabric monitor capacity -n asic{}".format(asic)
    else:
        cmd = "show fabric monitor capacity"
    # The output of this show command is:
    # # show fabric monitor capacity
    # Monitored fabric capacity threshold:  100%
    #
    #   ASIC    Operating     Total #    %    Last Event    Last Time
    #               Links    of Links
    # ------  -----------  ----------  ---  ------------  -----------
    #  asic0          112         112  100          None        Never
    cmd_output = duthost.shell(cmd, module_ignore_errors=True)["stdout"].split("\n")
    operating_links = 0
    for line in cmd_output:
        if not line:
            continue
        token = line.split()
        if token[0].startswith("asic"):
            operating_links = int(token[1])

    # get list of up/unisolated links by running "show fabric isolation" with Isolated=0
    # example output:
    # # show fabric isolation -n asic0
    #
    # asic0
    #   Local Link    Auto Isolated    Manual Isolated    Isolated
    # ------------  ---------------  -----------------  ----------
    #           20                0                  0           0
    #           21                0                  0           0
    up_link_list = []
    if duthost.is_multi_asic:
        cmd = "show fabric isolation -n asic{}".format(asic)
    else:
        cmd = "show fabric isolation"

    cmd_output = duthost.shell(cmd, module_ignore_errors=True)["stdout"].split("\n")
    for line in cmd_output:
        if not line:
            continue
        token = line.split()
        if not token[0].isdigit():
            continue
        localPort = token[0]
        isolateSt = token[3]
        if isolateSt == "0":
            up_link_list.append(localPort)

    if len(up_link_list) > 0:
        shutlink = random.choice(up_link_list)
    else:
        return

    # Start the test. Isolate a link and check if the capacity command get updated.
    # Unisolate the link and check if the capacity command get updated.
    if duthost.is_multi_asic:
        asicName = "asic{}".format(asic)
    else:
        asicName = ""
    try:
        # isolate a link on the chip
        cmd = "sudo config fabric port isolate {} {}".format(shutlink, asicName)
        cmd_output = duthost.shell(cmd, module_ignore_errors=True)["stdout"].split("\n")

        # check the output of "show fabric monitor capcity" command
        exp_links = operating_links - 1
        pytest_assert(wait_until(180, 30, 0, check_operational_link,
                                 duthost, asic, exp_links),
                      "The number of opertional links should be {}".format(exp_links))

        # unisolate the link so the capacity is back
        cmd = "sudo config fabric port unisolate {} {}".format(shutlink, asicName)
        cmd_output = duthost.shell(cmd, module_ignore_errors=True)["stdout"].split("\n")

        # check the output of "show fabric monitor capcity" command
        exp_links = operating_links
        pytest_assert(wait_until(180, 30, 0, check_operational_link,
                                 duthost, asic, exp_links),
                      "The number of opertional links should be {}".format(exp_links))
    finally:
        # clean up the test
        cmd = "sudo config fabric port unisolate {} {}".format(shutlink, asicName)
        cmd_output = duthost.shell(cmd, module_ignore_errors=True)["stdout"].split("\n")


def check_operational_link(host, asic, op_links):
    if host.is_multi_asic:
        cmd = "show fabric monitor capacity -n asic{}".format(asic)
    else:
        cmd = "show fabric monitor capacity"
    # Example output is:
    # # show fabric monitor capacity
    #
    #   ASIC    Operating     Total #    %    Last Event    Last Time
    #               Links    of Links
    # ------  -----------  ----------  ---  ------------  -----------
    #  asic0          112         112  100          None        Never
    cmd_output = host.shell(cmd, module_ignore_errors=True)["stdout"].split("\n")
    operating_links = 0
    for line in cmd_output:
        if not line:
            continue
        token = line.split()
        if token[0].startswith("asic"):
            operating_links = int(token[1])
    if operating_links == op_links:
        return True
    else:
        return False
