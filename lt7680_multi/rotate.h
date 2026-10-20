#pragma once
#include <stdint.h>

// 面の画像を r 回 (0〜3) 時計回りに 90 度回して映すとき、パネルの (x, y) に置く画素の、元の画像 (n x n、行優先) での番号。
// 時計回りはパネルを表から見た向き。test/test_rotate.cpp で確かめる
static inline uint32_t rotatedIndex(uint32_t x, uint32_t y, int r, uint32_t n = 480) {
  switch (r & 3) {
    case 1: return (n - 1 - x) * n + y;
    case 2: return (n - 1 - y) * n + (n - 1 - x);
    case 3: return x * n + (n - 1 - y);
    default: return y * n + x;
  }
}
