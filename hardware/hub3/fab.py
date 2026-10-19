"""Write the JLCPCB files to build/fab/: Gerbers and drill (zipped), and the
BOM and placement (CPL) for the parts with an LCSC number.

    /usr/bin/python3 fab.py

The XIAO's two 1x7 female sockets have no LCSC number here and are
soldered by hand. Check the FFC connectors' rotation in JLCPCB's placement
preview: their footprint is our own, not the one in JLCPCB's library.
"""
import csv
import os
import shutil
import subprocess

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build", "fab")
PCB = os.path.join(HERE, "hub3.kicad_pcb")
LAYERS = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    gerbers = os.path.join(OUT, "gerbers")
    os.makedirs(gerbers)
    subprocess.run(["kicad-cli", "pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask", "--use-drill-file-origin", "-o", gerbers + "/", PCB], check=True)
    subprocess.run(["kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th", "--drill-origin", "plot", "-o", gerbers + "/", PCB], check=True)
    shutil.make_archive(os.path.join(OUT, "hub3-gerbers"), "zip", gerbers)

    board = pcbnew.LoadBoard(PCB)
    origin = board.GetDesignSettings().GetAuxOrigin()
    rows = {}
    with open(os.path.join(OUT, "hub3-cpl.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
            lcsc = fp.GetFieldText("LCSC") if fp.HasField("LCSC") else ""
            if not lcsc:
                continue
            pos = fp.GetPosition()
            x = pcbnew.ToMM(pos.x - origin.x)
            y = -pcbnew.ToMM(pos.y - origin.y)  # JLCPCB: y up
            w.writerow([fp.GetReference(), f"{x:.3f}mm", f"{y:.3f}mm", "Top", f"{fp.GetOrientationDegrees() % 360:.0f}"])
            key = (fp.GetValue(), fp.GetFPID().GetLibItemName().wx_str(), lcsc)
            rows.setdefault(key, []).append(fp.GetReference())
    with open(os.path.join(OUT, "hub3-bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, lcsc), refs in sorted(rows.items(), key=lambda kv: kv[1][0]):
            w.writerow([value, ",".join(refs), footprint, lcsc])
    for name in sorted(os.listdir(OUT)):
        print(os.path.join(OUT, name))


if __name__ == "__main__":
    main()
