"""Route hub3.kicad_pcb with Freerouting and fill the GND zones.

    /usr/bin/python3 route.py [path/to/freerouting]

Exports the board as Specctra DSN, runs Freerouting headless, imports the
session back and fills the zones. The intermediate files go to build/.
Freerouting defaults to ~/.local/share/freerouting/2.4.1/... (the Linux
bundle with its own Java runtime; the plain jar needs Java 25).
"""
import os
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "hub3.kicad_pcb")
FREEROUTING = os.path.expanduser("~/.local/share/freerouting/2.4.1/freerouting-2.4.1-linux-x64/bin/freerouting")


def narrow_power_mm(board):
    """Length of +5V and +3V3 track narrower than the Power class's 0.6mm."""
    return sum(pcbnew.ToMM(t.GetLength()) for t in board.GetTracks()
               if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() in ("+5V", "+3V3") and pcbnew.ToMM(t.GetWidth()) < 0.6 - 1e-6)


def drc_clean():
    r = subprocess.run(["kicad-cli", "pcb", "drc", "--schematic-parity", "--severity-all", "--exit-code-violations",
                        "-o", os.path.join(HERE, "build", "drc.rpt"), PCB], capture_output=True, text=True)
    return r.returncode == 0


def main():
    if "--once" in sys.argv:
        args = [a for a in sys.argv[1:] if a != "--once"]
        board = route_once(args[0] if args else FREEROUTING)
        sys.exit(0 if narrow_power_mm(board) <= 5.0 else 3)
    # Each attempt runs in its own process: pcbnew's SWIG objects do not
    # survive loading and editing the board a second time in one process.
    # Freerouting does not route the same board the same way twice, and now
    # and then leaves an island or a gap, or necks a power track down for
    # long; route again until KiCad's DRC is clean and the necks are short.
    for attempt in range(1, 9):
        once = subprocess.run([sys.executable, os.path.abspath(__file__), "--once", *sys.argv[1:]])
        if once.returncode == 0 and drc_clean():
            print(f"clean after attempt {attempt}")
            return
        why = "long narrow power track" if once.returncode == 3 else ("routing failed" if once.returncode else "DRC not clean")
        print(f"attempt {attempt}: {why}, routing again")
    sys.exit("no clean routing in 8 attempts; see build/drc.rpt")


def route_once(fr):
    build = os.path.join(HERE, "build")
    os.makedirs(build, exist_ok=True)
    dsn, ses = os.path.join(build, "hub3.dsn"), os.path.join(build, "hub3.ses")
    board = pcbnew.LoadBoard(PCB)
    for t in list(board.GetTracks()):
        board.Remove(t)
    # Route GND as tracks too: with the zones in the DSN Freerouting leaves
    # GND to them, and the top zone breaks into islands between the tracks.
    zones = list(board.Zones())
    for z in zones:
        board.Remove(z)
    assert pcbnew.ExportSpecctraDSN(board, dsn), "DSN export failed"
    if os.path.exists(ses):
        os.remove(ses)
    subprocess.run([fr, "-de", dsn, "-do", ses, "-mp", "100", "--gui.enabled=false"], check=True)
    assert os.path.exists(ses), "Freerouting wrote no session"
    assert pcbnew.ImportSpecctraSES(board, ses), "SES import failed"
    for z in zones:
        board.Add(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    print(f"routed: {len(tracks)} tracks, {len(vias)} vias")
    return board


if __name__ == "__main__":
    main()
