"""Generate the hub3 KiCad project: one XIAO ESP32-S3 (in pin sockets), a
74HC138 and three 20-pin 1.0mm FFC connectors, one on each of three sides
of a square board, driving three ER-PCBA5981-1 boards (WIRING.md, 構成 3).

    /usr/bin/python3 make.py      # needs KiCad 10's pcbnew module

Writes the schematic, the board with every part placed and every pad on
its net (unrouted), the project's symbol and footprint libraries, and the
library tables. route.sh routes it; check.sh runs ERC, DRC and the
schematic parity check.

The parts and nets below are the single source for both the schematic
and the board.
"""
import json
import os
import re
import uuid

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "hub3"
KICAD = "/usr/share/kicad"
SIZE = 42.0  # square board, mm
ORIGIN = (100.0, 100.0)  # board's top left corner on the PCB sheet

# --- nets -------------------------------------------------------------------

# XIAO ESP32-S3 pin -> net (pin 1 = D0 ... 7 = D6, 8 = D7 ... 11 = D10, 12 3V3, 13 GND, 14 5V)
XIAO = {
    1: "SEL_A",  # D0 -> 74HC138 A
    2: "LCM_RESET",  # D1
    3: "SEL_B",  # D2 -> 74HC138 B
    4: "BL_CTRL",  # D3
    5: "LCD_SCLK",  # D4
    6: "LCD_DIN",  # D5
    7: "SEL_C",  # D6 -> 74HC138 C
    8: None,  # D7
    9: "LCM_SCLK",  # D8
    10: "LCM_SDO",  # D9 (MISO)
    11: "LCM_SDI",  # D10 (MOSI)
    12: "+3V3",
    13: "GND",
    14: "+5V",
}
XIAO_PINS = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "3V3", "GND", "5V"]

# 74HC138: board b's LT7680 on Y(b), its panel on Y(3 + b), Y7 idle (lt7680_multi)
HC138 = {
    1: "SEL_A", 2: "SEL_B", 3: "SEL_C", 4: "GND", 5: "GND", 6: "+3V3", 7: None, 8: "GND",
    9: None, 10: "LCD_CS2", 11: "LCD_CS1", 12: "LCD_CS0", 13: "LCM_SCS2", 14: "LCM_SCS1", 15: "LCM_SCS0", 16: "+3V3",
}


def ffc(board):
    """ER-PCBA5981-1 CON1 pin -> net, for the FFC to board `board`."""
    return {
        1: "GND", 2: "GND", 3: "+5V", 4: "+5V", 5: f"LCM_SCS{board}", 6: "LCM_SDO", 7: "LCM_SDI", 8: "LCM_SCLK",
        9: "BL_CTRL", 10: None, 11: "LCM_RESET", 12: None, 13: None, 14: None, 15: None, 16: f"LCD_CS{board}",
        17: None, 18: "LCD_DIN", 19: "LCD_SCLK", 20: None,
    }


# --- parts ------------------------------------------------------------------
# ref: (symbol, value, footprint, LCSC part, pin -> net, (x, y, rotation) on the board relative to its top left corner)
C = SIZE / 2
FFC_FP = "cubic-earth:FFC_1.0mm_20P_Bottom_C2998680"
PARTS = {
    "J1": ("cubic-earth:FFC_20P", "LCD0", FFC_FP, "C2998680", ffc(0), (5.5, C, 90)),
    "J2": ("cubic-earth:FFC_20P", "LCD1", FFC_FP, "C2998680", ffc(1), (C, 5.5, 0)),
    "J3": ("cubic-earth:FFC_20P", "LCD2", FFC_FP, "C2998680", ffc(2), (SIZE - 5.5, C, -90)),
    "U1": ("74xx:74HC138", "74HC138", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", "C2674688", HC138, (C, 14.0, 90)),
    "U2": ("cubic-earth:XIAO_ESP32S3", "XIAO ESP32S3", "cubic-earth:XIAO_Socket_2x7_P2.54mm", "", XIAO, (C, SIZE - 10.6, 0)),
    "C1": ("Device:C", "100nF", "Capacitor_SMD:C_0603_1608Metric", "C14663", {1: "+3V3", 2: "GND"}, (C + 7.5, 14.0, 90)),
    "C2": ("Device:C", "10uF", "Capacitor_SMD:C_0805_2012Metric", "C15850", {1: "+5V", 2: "GND"}, (33.4, SIZE - 4.5, 90)),
}
HOLES = [(3.5, 3.5), (SIZE - 3.5, 3.5), (3.5, SIZE - 3.5), (SIZE - 3.5, SIZE - 3.5)]


def uid():
    return str(uuid.uuid4())


# --- S-expression helpers ---------------------------------------------------


def find_block(text, head):
    """Return the balanced (...) block starting with `head`."""
    i = text.index(head)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
        elif text[j] == '"':
            j = text.index('"', j + 1)
    raise ValueError(head)


def lib_symbol(lib, name, path):
    block = find_block(open(path).read(), f'(symbol "{name}"')
    assert "(extends" not in block, name
    return block.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


def pin_names(block):
    """pin number -> pin name."""
    return {m.group(2): m.group(1) for m in re.finditer(r'\(name "([^"]*)".*?\(number "([^"]+)"', block, re.S)}


def unconnected_net(ref, num, name):
    """The name KiCad gives the net of an unconnected pin."""
    return f"unconnected-({ref}-{name}-Pad{num})" if name and name != num else f"unconnected-({ref}-Pad{num})"


def pins_of(block):
    """pin number -> (x, y) connection point, symbol coordinates (y up)."""
    pins = {}
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) [-\d.]+\).*?\(number "([^"]+)"', block, re.S):
        pins[m.group(3)] = (float(m.group(1)), float(m.group(2)))
    return pins


# --- project symbol library ---------------------------------------------------


def box_symbol(name, ref, left, right, width=15.24):
    """A rectangle with pins: left/right are lists of (number, name, type), top to bottom."""
    n = max(len(left), len(right))
    top = (n - 1) * 2.54 / 2
    h = top + 2.54
    out = [f'(symbol "{name}" (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
           f'(property "Reference" "{ref}" (at 0 {h + 1.27:.2f} 0) (effects (font (size 1.27 1.27))))',
           f'(property "Value" "{name}" (at 0 {-h - 1.27:.2f} 0) (effects (font (size 1.27 1.27))))',
           '(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
           '(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
           f'(symbol "{name}_0_1" (rectangle (start {-width / 2:.2f} {h:.2f}) (end {width / 2:.2f} {-h:.2f}) (stroke (width 0.254) (type default)) (fill (type background))))',
           f'(symbol "{name}_1_1"']
    for side, pins in ((-1, left), (1, right)):
        for i, (num, pname, ptype) in enumerate(pins):
            x = side * (width / 2 + 2.54)
            y = top - i * 2.54
            ang = 0 if side < 0 else 180
            out.append(f'(pin {ptype} line (at {x:.2f} {y:.2f} {ang}) (length 2.54) (name "{pname}" (effects (font (size 1.27 1.27)))) (number "{num}" (effects (font (size 1.27 1.27)))))')
    out.append("))")
    return "\n".join(out)


def project_symbols():
    xiao_left = [(str(i), XIAO_PINS[i - 1], "bidirectional") for i in range(1, 8)]
    xiao_right = [("14", "5V", "power_out"), ("13", "GND", "power_out"), ("12", "3V3", "power_out")] + [
        (str(i), XIAO_PINS[i - 1], "bidirectional") for i in (11, 10, 9, 8)]
    ffc_left = [(str(i), f"{i}", "passive") for i in range(1, 21)]
    return {
        "XIAO_ESP32S3": box_symbol("XIAO_ESP32S3", "U", xiao_left, xiao_right),
        "FFC_20P": box_symbol("FFC_20P", "J", ffc_left, [], width=5.08),
    }


def write_symbol_lib(symbols):
    body = "\n".join(symbols.values())
    with open(os.path.join(HERE, "cubic-earth.kicad_sym"), "w") as f:
        f.write(f"(kicad_symbol_lib (version 20231120) (generator \"make.py\")\n{body}\n)\n")


# --- project footprints -------------------------------------------------------


def write_footprints():
    os.makedirs(os.path.join(HERE, "cubic-earth.pretty"), exist_ok=True)
    # BOOMELE 1.0-20P bottom contact (LCSC C2998680), from its drawing
    # (tmp/docs/C2998680.pdf, "FPC1.0-2-nP 下接"): signal pads 0.60 x 2.2 at
    # 1.00 pitch; hold-down pads 1.8 x 2.6, their centres 2.3 outside pins 1
    # and 20 and about 2.26 toward the body. Origin: the back edge of the
    # body, where the leads come out; the body (5.5 deep) and the cable
    # opening are toward -y. Pin 1 is on the left seen from above with the
    # opening up.
    lines = ['(footprint "FFC_1.0mm_20P_Bottom_C2998680" (version 20240108) (generator "make.py") (layer "F.Cu")',
             '(descr "FFC/FPC connector, 20 pins, 1.0mm pitch, bottom contact, right angle, BOOMELE 1.0-20P (LCSC C2998680)")',
             '(attr smd)',
             '(property "Reference" "REF**" (at 0 -6.6 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
             '(property "Value" "FFC_20P" (at 0 -3 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
             '(fp_rect (start -12.5 -5.5) (end 12.5 0) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))',
             '(fp_rect (start -13.1 -5.8) (end 13.1 2.4) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))',
             '(fp_line (start -10.6 2.2) (end -10.6 1.2) (stroke (width 0.15) (type default)) (layer "F.SilkS"))',
             '(fp_text user "1" (at -10.9 3.1 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))']
    for p in range(1, 21):
        lines.append(f'(pad "{p}" smd roundrect (at {-9.5 + (p - 1):.2f} 0.9) (size 0.6 2.2) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.15))')
    for x in (-11.8, 11.8):
        lines.append(f'(pad "" smd rect (at {x:.2f} -1.36) (size 1.8 2.6) (layers "F.Cu" "F.Paste" "F.Mask"))')
    lines.append(")")
    with open(os.path.join(HERE, "cubic-earth.pretty", "FFC_1.0mm_20P_Bottom_C2998680.kicad_mod"), "w") as f:
        f.write("\n".join(lines) + "\n")

    # XIAO ESP32-S3 on two 1x7 female sockets, rows 15.24 apart (Seeed's
    # XIAO-ESP32-S3-DIP pad positions), USB-C toward +y. Pin 1 (D0) and pin 14
    # (5V) are at the USB end.
    lines = ['(footprint "XIAO_Socket_2x7_P2.54mm" (version 20240108) (generator "make.py") (layer "F.Cu")',
             '(descr "Seeed XIAO (ESP32-S3) in two 1x7 2.54mm female pin sockets, USB-C toward +y")',
             '(attr through_hole)',
             '(property "Reference" "REF**" (at 0 -12 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
             '(property "Value" "XIAO" (at 0 0 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
             '(fp_rect (start -8.95 -10.47) (end 8.95 10.6) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))',
             '(fp_rect (start -4.5 10.6) (end 4.5 12.1) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))',
             '(fp_text user "USB" (at 0 8.5 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
             '(fp_rect (start -9.2 -10.7) (end 9.2 12.3) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))']
    for x in (-7.62, 7.62):
        lines.append(f'(fp_rect (start {x - 1.33:.2f} -10.29) (end {x + 1.33:.2f} 10.29) (stroke (width 0.15) (type default)) (fill none) (layer "F.SilkS"))')
    for p in range(1, 15):
        if p <= 7:
            x, y = 7.62, 7.62 - (p - 1) * 2.54
        else:
            x, y = -7.62, -7.62 + (p - 8) * 2.54
        shape = "rect" if p == 1 else "circle"
        lines.append(f'(pad "{p}" thru_hole {shape} (at {x:.2f} {y:.2f}) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask"))')
    lines.append('(fp_text user "D0" (at 10.2 7.62 90) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))')
    lines.append('(fp_text user "5V" (at -10.2 7.62 90) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))')
    lines.append(")")
    with open(os.path.join(HERE, "cubic-earth.pretty", "XIAO_Socket_2x7_P2.54mm.kicad_mod"), "w") as f:
        f.write("\n".join(lines) + "\n")


# --- schematic ----------------------------------------------------------------

# on the 2.54mm grid so every pin lands on the connection grid
SCH_POS = {ref: (round(x / 2.54) * 2.54, round(y / 2.54) * 2.54) for ref, (x, y) in
           {"U2": (60, 70), "U1": (130, 70), "C1": (160, 60), "C2": (160, 85), "J1": (40, 140), "J2": (100, 140), "J3": (160, 140)}.items()}


def all_libs(symbols):
    libs = {
        "74xx:74HC138": lib_symbol("74xx", "74HC138", f"{KICAD}/symbols/74xx.kicad_sym"),
        "Device:C": lib_symbol("Device", "C", f"{KICAD}/symbols/Device.kicad_sym"),
    }
    for name, block in symbols.items():
        libs[f"cubic-earth:{name}"] = block.replace(f'(symbol "{name}"', f'(symbol "cubic-earth:{name}"', 1)
    return libs


def write_schematic(libs):
    root = uid()
    out = [f'(kicad_sch (version 20231120) (generator "make.py") (generator_version "10.0") (uuid "{root}") (paper "A4")',
           '(title_block (title "cubic-earth hub3") (rev "A") (comment 1 "XIAO ESP32-S3 + 74HC138 + 3 x FFC to ER-PCBA5981-1"))',
           "(lib_symbols", *libs.values(), ")"]
    for ref, (lib_id, value, fp, lcsc, nets, _) in PARTS.items():
        x, y = SCH_POS[ref]
        pins = pins_of(libs[lib_id])
        props = [("Reference", ref, 0, -1), ("Value", value, 0, 1), ("Footprint", fp, 0, 0), ("Datasheet", "", 0, 0)]
        if lcsc:
            props.append(("LCSC", lcsc, 0, 0))
        out.append(f'(symbol (lib_id "{lib_id}") (at {x:.2f} {y:.2f} 0) (unit 1) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "{uid()}")')
        top = min(-py for _, py in pins.values()) + y
        bottom = max(-py for _, py in pins.values()) + y
        for k, (pname, pval, _, where) in enumerate(props):
            hide = " hide" if where == 0 else ""
            py = top - 3.81 if where < 0 else (bottom + 3.81 if where > 0 else y)
            out.append(f'(property "{pname}" "{pval}" (at {x:.2f} {py:.2f} 0) (effects (font (size 1.27 1.27)){hide}))')
        for num in pins:
            out.append(f'(pin "{num}" (uuid "{uid()}"))')
        out.append(f'(instances (project "{NAME}" (path "/{root}" (reference "{ref}") (unit 1)))))')
        for num, (px, py) in pins.items():
            net = nets.get(int(num))
            ax, ay = x + px, y - py
            if net is None:
                out.append(f'(no_connect (at {ax:.2f} {ay:.2f}) (uuid "{uid()}"))')
                continue
            left = px < 0 or (abs(px) < 1e-6 and py > 0)
            ang, just = (180, "right") if left else (0, "left")
            out.append(f'(global_label "{net}" (shape passive) (at {ax:.2f} {ay:.2f} {ang}) (effects (font (size 1.27 1.27)) (justify {just})) (uuid "{uid()}"))')
    out.append(f'(sheet_instances (path "/" (page "1")))')
    out.append(")")
    with open(os.path.join(HERE, f"{NAME}.kicad_sch"), "w") as f:
        f.write("\n".join(out) + "\n")


# --- board --------------------------------------------------------------------


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))


def write_board(libs):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_MinClearance = mm(0.15)
    ds.m_ViasMinSize = mm(0.6)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_CopperEdgeClearance = mm(0.3)
    # fabrication files are written from the board's lower left corner
    ds.SetAuxOrigin(pt(0, SIZE))
    ds.SetGridOrigin(pt(0, SIZE))
    nets = {}

    def net(name):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    for ref, (_, value, fp_id, lcsc, pin_nets, (x, y, rot)) in PARTS.items():
        lib, name = fp_id.split(":")
        path = os.path.join(HERE, "cubic-earth.pretty") if lib == "cubic-earth" else f"{KICAD}/footprints/{lib}.pretty"
        fp = pcbnew.FootprintLoad(path, name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(value)
        if lcsc:
            fp.SetField("LCSC", lcsc)
            field = fp.GetField("LCSC")
            field.SetVisible(False)
            field.SetLayer(pcbnew.F_Fab)
        names = pin_names(libs[PARTS[ref][0]])
        board.Add(fp)
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            num = pad.GetNumber()
            if num:
                # the schematic names an unconnected pin's net after the pin
                pad.SetNet(net(pin_nets.get(int(num)) or unconnected_net(ref, num, names.get(num))))
    for i, (x, y) in enumerate(HOLES, 1):
        fp = pcbnew.FootprintLoad(f"{KICAD}/footprints/MountingHole.pretty", "MountingHole_2.2mm_M2")
        fp.SetFPID(pcbnew.LIB_ID("MountingHole", "MountingHole_2.2mm_M2"))
        fp.SetReference(f"H{i}")
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        fp.SetBoardOnly(True)
        fp.SetExcludedFromBOM(True)
        fp.SetExcludedFromPosFiles(True)
        board.Add(fp)
        fp.SetPosition(pt(x, y))

    corners = [(0, 0), (SIZE, 0), (SIZE, SIZE), (0, SIZE)]
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pt(x0, y0))
        seg.SetEnd(pt(x1, y1))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    for text, x, y, size, layer in [("cubic-earth hub3 rev A", C, C, 1.2, pcbnew.B_SilkS), ("USB", C, SIZE - 1.2, 0.8, pcbnew.F_SilkS)]:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetPosition(pt(x, y))
        t.SetLayer(layer)
        t.SetMirrored(layer == pcbnew.B_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(0.15))
        board.Add(t)

    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(net("GND"))
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in corners:
            p = pt(x, y)
            outline.Append(p.x, p.y)
        zone.SetLocalClearance(mm(0.3))
        zone.SetMinThickness(mm(0.2))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        board.Add(zone)

    board.Save(os.path.join(HERE, f"{NAME}.kicad_pcb"))


def write_project():
    pro = {
        "board": {"design_settings": {"rules": {"min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.6,
                                                "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.3}}},
        "net_settings": {
            "classes": [
                {"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3},
                {"name": "Power", "clearance": 0.2, "track_width": 0.6, "via_diameter": 0.8, "via_drill": 0.4},
            ],
            "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in ("+5V", "GND", "+3V3")],
        },
        "meta": {"filename": f"{NAME}.kicad_pro", "version": 1},
    }
    with open(os.path.join(HERE, f"{NAME}.kicad_pro"), "w") as f:
        json.dump(pro, f, indent=2)
    with open(os.path.join(HERE, "sym-lib-table"), "w") as f:
        f.write('(sym_lib_table (version 7)\n'
                '  (lib (name "cubic-earth") (type "KiCad") (uri "${KIPRJMOD}/cubic-earth.kicad_sym") (options "") (descr ""))\n'
                '  (lib (name "74xx") (type "KiCad") (uri "${KICAD10_SYMBOL_DIR}/74xx.kicad_sym") (options "") (descr ""))\n'
                '  (lib (name "Device") (type "KiCad") (uri "${KICAD10_SYMBOL_DIR}/Device.kicad_sym") (options "") (descr ""))\n)\n')
    with open(os.path.join(HERE, "fp-lib-table"), "w") as f:
        f.write('(fp_lib_table (version 7)\n'
                '  (lib (name "cubic-earth") (type "KiCad") (uri "${KIPRJMOD}/cubic-earth.pretty") (options "") (descr ""))\n')
        for lib in ("Package_SO", "Capacitor_SMD", "MountingHole"):
            f.write(f'  (lib (name "{lib}") (type "KiCad") (uri "${{KICAD10_FOOTPRINT_DIR}}/{lib}.pretty") (options "") (descr ""))\n')
        f.write(")\n")


def main():
    symbols = project_symbols()
    libs = all_libs(symbols)
    write_symbol_lib(symbols)
    write_footprints()
    write_project()
    write_schematic(libs)
    write_board(libs)
    print(f"wrote {NAME}.kicad_sch, {NAME}.kicad_pcb (unrouted)")


if __name__ == "__main__":
    main()
