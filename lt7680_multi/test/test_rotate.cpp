// Host test for rotate.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_rotate test/test_rotate.cpp && /tmp/test_rotate
#include <cassert>
#include <cstdio>
#include "../rotate.h"

int main() {
  const uint32_t n = 3;
  // src (row-major):  0 1 2 / 3 4 5 / 6 7 8
  const uint32_t want[4][9] = {
      {0, 1, 2, 3, 4, 5, 6, 7, 8},  // as is
      {6, 3, 0, 7, 4, 1, 8, 5, 2},  // a quarter turn clockwise: the left column becomes the top row
      {8, 7, 6, 5, 4, 3, 2, 1, 0},  // half turn
      {2, 5, 8, 1, 4, 7, 0, 3, 6},  // a quarter turn counterclockwise
  };
  for (int r = 0; r < 4; r++)
    for (uint32_t y = 0; y < n; y++)
      for (uint32_t x = 0; x < n; x++) assert(rotatedIndex(x, y, r, n) == want[r][y * n + x]);
  // every rotation of the full face is a permutation
  const uint32_t m = 480;
  static bool seen[480 * 480];
  for (int r = 0; r < 4; r++) {
    for (auto &s : seen) s = false;
    for (uint32_t y = 0; y < m; y++)
      for (uint32_t x = 0; x < m; x++) {
        uint32_t i = rotatedIndex(x, y, r, m);
        assert(i < m * m && !seen[i]);
        seen[i] = true;
      }
  }
  // panelOf is the inverse: the panel point that shows source pixel (sx, sy)
  for (int r = 0; r < 4; r++)
    for (uint32_t y = 0; y < m; y += 7)
      for (uint32_t x = 0; x < m; x += 5) {
        uint32_t i = rotatedIndex(x, y, r, m);
        uint32_t px, py;
        panelOf(i % m, i / m, r, &px, &py, m);
        assert(px == x && py == y);
      }
  std::puts("rotate ok");
}
