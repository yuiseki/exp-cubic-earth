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


def main():
    fr = sys.argv[1] if len(sys.argv) > 1 else FREEROUTING
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


if __name__ == "__main__":
    main()
