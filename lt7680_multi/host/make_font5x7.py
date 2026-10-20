"""font5x7.h from the X11 misc-fixed 5x7 font (public domain), ASCII 32-95.

    uv run -q --no-project --with pillow python host/make_font5x7.py /usr/share/fonts/X11/misc/5x7-ISO8859-1.pcf.gz > font5x7.h
"""
import gzip
import sys

from PIL import PcfFontFile

pcf = PcfFontFile.PcfFontFile(gzip.open(sys.argv[1]))
print("#pragma once")
print("#include <stdint.h>")
print("// 5x7 の文字 (X11 misc-fixed 5x7、パブリックドメイン、host/make_font5x7.py で作る)。")
print("// ASCII 32〜95 (空白、数字、英大文字、記号)。1 文字 7 行で、各行の下位 5 ビットが左から右 (ビット 4 が左端)")
print("static const uint8_t FONT5X7[64][7] = {")
for code in range(32, 96):
    im = pcf.glyph[code][3]  # every glyph is a full 5x7 cell (4 columns of ink, 1 of spacing)
    rows = [sum((1 if im.getpixel((x, y)) else 0) << (4 - x) for x in range(5)) for y in range(7)]
    print("  {" + ", ".join(f"0x{r:02X}" for r in rows) + "},  // " + repr(chr(code)))
print("};")
