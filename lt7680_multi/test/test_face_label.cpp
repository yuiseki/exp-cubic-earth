// Host test for face_label.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_face_label test/test_face_label.cpp && /tmp/test_face_label
#include <cassert>
#include <cstdio>
#include "../face_label.h"

// is any pixel of the w x h box at (x0, y0) black on board b?
static bool inked(int b, int x0, int y0, int w, int h) {
  for (int y = y0; y < y0 + h; y++)
    for (int x = x0; x < x0 + w; x++)
      if (faceLabelColor(b, x, y) == 0x0000) return true;
  return false;
}

int main() {
  // the corners and the gaps between the labels are white
  assert(faceLabelColor(0, 0, 0) == 0xFFFF && faceLabelColor(2, 479, 479) == 0xFFFF);
  assert(!inked(1, 0, 0, 120, 120) && !inked(1, 360, 360, 120, 120));
  // the letter in the middle: A, B, C for boards 0, 1, 2, and they differ
  assert(inked(0, 190, 190, 100, 100));
  int diff = 0;
  for (int y = 140; y < 340; y += 4)
    for (int x = 140; x < 340; x += 4) diff += faceLabelColor(0, x, y) != faceLabelColor(1, x, y);
  assert(diff > 0);
  // a numeral near the middle of each edge (1 top, 2 right, 3 bottom, 4 left), nothing right at the edge
  assert(inked(0, 200, 10, 80, 80));    // 1
  assert(inked(0, 390, 200, 80, 80));   // 2
  assert(inked(0, 200, 390, 80, 80));   // 3
  assert(inked(0, 10, 200, 80, 80));    // 4
  assert(!inked(0, 0, 0, 480, 4) && !inked(0, 0, 0, 4, 480) && !inked(0, 476, 0, 4, 480) && !inked(0, 0, 476, 480, 4));
  // the top numeral is a 1: its top row lights only the middle column of the glyph
  const int S = FACE_LABEL_EDGE_SCALE, x0 = 240 - 5 * S / 2, y0 = FACE_LABEL_EDGE_INSET;
  assert(faceLabelColor(0, x0 + 2 * S + S / 2, y0 + S / 2) == 0x0000);
  assert(faceLabelColor(0, x0 + S / 2, y0 + S / 2) == 0xFFFF);
  puts("test_face_label: ok");
}
