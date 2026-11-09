// Host test for face_label.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_face_label test/test_face_label.cpp && /tmp/test_face_label
#include <cassert>
#include <cstdio>
#include <cstring>
#include "../face_label.h"

// is any pixel of the w x h box at (x0, y0) black on board b of the unit?
static bool inked(int b, const char *unit, int x0, int y0, int w, int h) {
  for (int y = y0; y < y0 + h; y++)
    for (int x = x0; x < x0 + w; x++)
      if (faceLabelColor(b, unit, x, y) == 0x0000) return true;
  return false;
}

int main() {
  const char *U = "UNIT-01-N";

  // the whole picture is the one agreed as boot_label_example5.png (made by a separate script from the same 5x7 font):
  // 12025 black pixels, and the sum over them of x * 7 + y * 13
  {
    unsigned long long count = 0, sum = 0;
    for (int y = 0; y < 480; y++)
      for (int x = 0; x < 480; x++)
        if (faceLabelColor(0, U, x, y) == 0x0000) { count++; sum += (unsigned long long)x * 7 + (unsigned long long)y * 13; }
    assert(count == 12025);
    assert(sum == 58006500ULL);
  }

  // every pixel is black or white, and the corners are white
  for (int y = 0; y < 480; y += 3)
    for (int x = 0; x < 480; x += 3) {
      uint16_t c = faceLabelColor(1, U, x, y);
      assert(c == 0x0000 || c == 0xFFFF);
    }
  assert(faceLabelColor(0, U, 0, 0) == 0xFFFF && faceLabelColor(2, U, 479, 479) == 0xFFFF);
  assert(!inked(1, U, 0, 0, 90, 90) && !inked(1, U, 390, 390, 90, 90));

  // the big letter in the middle: A, B, C for boards 0, 1, 2, and they differ
  assert(inked(0, U, 190, 170, 100, 140));
  int diff = 0;
  for (int y = 170; y < 310; y += 4)
    for (int x = 190; x < 290; x += 4) diff += faceLabelColor(0, U, x, y) != faceLabelColor(1, U, x, y);
  assert(diff > 0);

  // the unit name above the letter, CUBIC-EARTH below it, and the unit name tells the modules apart
  assert(inked(0, U, 100, 94, 280, 36));
  assert(inked(0, U, 70, 350, 340, 36));
  assert(!inked(0, U, 0, 60, 480, 30) && !inked(0, U, 0, 135, 480, 30));  // clear above and below the unit name
  int d2 = 0;
  for (int y = 94; y < 130; y++)
    for (int x = 100; x < 380; x++) d2 += faceLabelColor(0, "UNIT-01-N", x, y) != faceLabelColor(0, "UNIT-01-S", x, y);
  assert(d2 > 0);

  // a numeral near the middle of each edge (1 top, 2 right, 3 bottom, 4 left), nothing right at the edge
  assert(inked(0, U, 220, 8, 40, 36));     // 1
  assert(inked(0, U, 430, 222, 40, 36));   // 2
  assert(inked(0, U, 220, 436, 40, 36));   // 3
  assert(inked(0, U, 10, 222, 40, 36));    // 4
  assert(!inked(0, U, 0, 0, 480, 4) && !inked(0, U, 0, 0, 4, 480) && !inked(0, U, 476, 0, 4, 480) && !inked(0, U, 0, 476, 480, 4));
  // the top numeral is a 1: its top row lights only the middle column of the glyph
  const int S = FACE_LABEL_EDGE_SCALE, x0 = 240 - 5 * S / 2, y0 = FACE_LABEL_TB - 7 * S / 2;
  assert(faceLabelColor(0, U, x0 + 2 * S + S / 2, y0 + S / 2) == 0x0000);
  assert(faceLabelColor(0, U, x0 + S / 2, y0 + S / 2) == 0xFFFF);

  // unit names from the MAC address: the two known modules, and a hex tail for any other
  char name[16];
  const uint8_t north[6] = {0xB8, 0xF8, 0x62, 0xF8, 0xDB, 0xA0}, south[6] = {0x8C, 0xBF, 0xEA, 0x8F, 0x3F, 0x38}, other[6] = {1, 2, 3, 4, 0xAB, 0x0C};
  unitName(north, name, sizeof name);
  assert(strcmp(name, "UNIT-01-N") == 0);
  unitName(south, name, sizeof name);
  assert(strcmp(name, "UNIT-01-S") == 0);
  unitName(other, name, sizeof name);
  assert(strcmp(name, "UNIT-AB0C") == 0);
  char tiny[4];
  unitName(north, tiny, sizeof tiny);
  assert(strlen(tiny) == 3);
  puts("test_face_label: ok");
}
