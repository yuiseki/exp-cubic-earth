// Host test for icons.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_icons test/test_icons.cpp && /tmp/test_icons
#include <cassert>
#include <cstdio>
#include "../icons.h"

int main() {
  // screen directions (y grows downwards), clockwise from up
  assert(iconDir(0, -5) == 0);
  assert(iconDir(5, -5) == 1);
  assert(iconDir(5, 0) == 2);
  assert(iconDir(5, 5) == 3);
  assert(iconDir(0, 5) == 4);
  assert(iconDir(-5, 5) == 5);
  assert(iconDir(-5, 0) == 6);
  assert(iconDir(-5, -5) == 7);
  assert(iconDir(1, -10) == 0);
  assert(iconDir(-1, -10) == 0);
  // the nose points where the plane goes
  assert(iconPixel(false, 0, 5, 0));
  assert(iconPixel(false, 2, 10, 5));
  assert(iconPixel(false, 4, 5, 10));
  assert(iconPixel(false, 6, 0, 5));
  assert(!iconPixel(false, 0, 0, 0));
  // each quarter turn is the one before rotated clockwise: new(x, y) = old(y, N-1-x)
  const int N = ICON_N;
  for (int d = 0; d < 6; d++)
    for (int y = 0; y < N; y++)
      for (int x = 0; x < N; x++) assert(iconPixel(false, d + 2, x, y) == iconPixel(false, d, y, N - 1 - x));
  // the plane is symmetric about its own axis (up: left-right mirror)
  for (int y = 0; y < N; y++)
    for (int x = 0; x < N; x++) assert(iconPixel(false, 0, x, y) == iconPixel(false, 0, N - 1 - x, y));
  // a diagonal plane mirrors across its diagonal (up-right: swap x and y after flipping)
  for (int y = 0; y < N; y++)
    for (int x = 0; x < N; x++) assert(iconPixel(false, 1, x, y) == iconPixel(false, 1, N - 1 - y, N - 1 - x));
  // the ship turns by quarter turns only (odd dir rounds down), and keel-down for dir 0
  int on = 0;
  for (int d = 0; d < 8; d += 2)
    for (int y = 0; y < N; y++)
      for (int x = 0; x < N; x++) {
        assert(iconPixel(true, d + 1, x, y) == iconPixel(true, d, x, y));
        if (d < 6) assert(iconPixel(true, d + 2, x, y) == iconPixel(true, d, y, N - 1 - x));
        on += iconPixel(true, d, x, y);
      }
  assert(on > 0);
  for (int x = 0; x < N; x++) assert(iconPixel(true, 0, x, 6));
  // southOnPanel's q (0 down, 1 right, 2 up, 3 left) -> the dir that puts the keel there
  assert(shipDirForSouth(0) == 0);
  assert(shipDirForSouth(1) == 6);
  assert(shipDirForSouth(2) == 4);
  assert(shipDirForSouth(3) == 2);
  // keel (row 8, the narrow bottom of the hull) ends up on the south side: q 1 = right
  assert(iconPixel(true, shipDirForSouth(1), 8, 5));
  assert(!iconPixel(true, shipDirForSouth(1), 1, 5));  // the funnel side (left after the turn) has no hull at the edge
  puts("test_icons: ok");
}
