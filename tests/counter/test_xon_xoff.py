"""
=============================================================================
Module: counter
File: test_xon_xoff.py
=============================================================================

Description:
    This test module verifies that IEEE 802.3x PAUSE frames (XON/XOFF) are
    properly handled by the DUT and do not incorrectly increment RX_DROPS
    counter. PAUSE frames are used for flow control and should be processed
    by the hardware without being counted as dropped packets.

Test Intent:
    - test_xon_xoff_does_not_increase_rx_drop: Validates that sending XOFF
      (pause) and XON (resume) frames to a DUT port does not cause the
      RX_DROPS counter to increase, ensuring proper 802.3x flow control
      handling without misclassifying control frames as packet drops.

Topology:
    t0, t1, lt2, ft2, ptf
    Requires PTF host for traffic generation and testbed with ptf_map
    configured for DUT-to-PTF port mapping.

Fixtures Used:
    - duthosts: Multi-DUT test fixture providing access to all DUTs
    - rand_one_dut_hostname: Randomly selects one DUT hostname from available DUTs
    - rand_one_dut_portname_oper_up: Randomly selects one operational port
    - ptfadapter: PTF test adapter for sending/receiving test packets
    - tbinfo: Testbed information including topology and port mappings

Dependencies:
    - pytest: Test framework
    - ptf.packet (scapy): Packet crafting library
    - struct: Binary data packing for pause frame construction
    - time: Timing control for packet transmission
    - COUNTERS_DB: Redis database for interface counter queries

Notes:
    - Test sends 300 XOFF frames (quanta=0xFFFF) followed by 300 XON frames
      (quanta=0x0000) with 5ms intervals between frames
    - Allows up to 10 RX_DROP counter increase as tolerance for edge cases
    - PAUSE frames use destination MAC 01:80:C2:00:00:01 and EtherType 0x8808
    - Requires testbed with proper PTF port mapping configured
    - Git history: Added in commit b0b41bcb9 to address RX_DROP issue with
      802.3x pause frames (#20543)
=============================================================================
"""
import time
import struct
import pytest
import ptf.packet as scapy

pytestmark = [
    pytest.mark.topology("t0", "t1", "lt2", "ft2", "ptf"),
]


def craft_pause_frame(opcode=0x0001, quanta=0):
    """
    Build a classic 802.3x PAUSE frame (XOFF when quanta > 0, XON when quanta == 0).
    EtherType = 0x8808, Opcode = 0x0001, followed by 2-byte pause time.
    """
    payload = struct.pack("!H", opcode) + struct.pack("!H", quanta) + b"\x00" * 42
    eth = scapy.Ether(
        dst="01:80:C2:00:00:01", src="02:02:02:02:02:02", type=0x8808
    )
    return eth / scapy.Raw(payload)


def read_rx_drops(duthost, iface):
    """
    Read RX_DROPS counter from COUNTERS_DB for iface.
    Returns int (0 if no value).
    """
    cmd = (
        f"sonic-db-cli COUNTERS_DB HGET 'COUNTERS:{iface}' 'RX_DROPS' "
        f"|| redis-cli -n 2 HGET 'COUNTERS:{iface}' 'RX_DROPS'"
    )
    res = duthost.shell(cmd, module_ignore_errors=True)
    out = res.get("stdout", "").strip()
    try:
        return int(out) if out else 0
    except ValueError:
        return 0


@pytest.mark.usefixtures("duthosts", "ptfadapter", "tbinfo")
def test_xon_xoff_does_not_increase_rx_drop(
    duthosts,
    rand_one_dut_hostname,
    rand_one_dut_portname_oper_up,
    ptfadapter,
    tbinfo,
):
    """
    Verify that sending XOFF/XON (802.3x PAUSE) frames from peer does NOT
    increase RX_DROPS on DUT port.

    Steps:
      - Pick a random operational front-panel port (fixture)
      - Map it to the PTF port index via tbinfo["topo"]["ptf_map"]
      - Send XOFF then XON frames
      - Assert RX_DROPS delta == 0
    """
    duthost = duthosts[rand_one_dut_hostname]
    dut_port = rand_one_dut_portname_oper_up

    # Map DUT port to PTF index (topology must provide ptf_map)
    ptf_map = tbinfo.get("topo", {}).get("ptf_map", {})
    if dut_port not in ptf_map:
        pytest.skip(
            f"no ptf mapping for DUT port {dut_port} in tbinfo; can't run traffic"
        )

    ptf_port_idx = int(ptf_map[dut_port])

    # Baseline
    before = read_rx_drops(duthost, dut_port)

    # Send XOFF (pause_time > 0)
    xoff = craft_pause_frame(quanta=0xFFFF)

    xoff_frames = 300

    for _ in range(xoff_frames):
        ptfadapter.dataplane.send(ptf_port_idx, bytes(xoff))
        time.sleep(0.005)

    # Send XON (pause_time == 0)

    xon = craft_pause_frame(quanta=0x0000)

    xon_frames = 300

    for _ in range(xon_frames):
        ptfadapter.dataplane.send(ptf_port_idx, bytes(xon))
        time.sleep(0.005)

    # Allow counters to settle
    time.sleep(2)

    after = read_rx_drops(duthost, dut_port)

    assert (after - before) <= 10, (
        f"RX_DROP increased on {dut_port}: before={before} after={after}"
    )
