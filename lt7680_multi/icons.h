#pragma once
// #t の本物の飛行機と船の印 (11x11)。飛行機は進む向きに 8 方向で回し、船は横から見た形で回さない。
// 飛行機の 2 枚 (上向きと右上向き) は、胴体・後退翼・尾翼の式を 4x4 の点で塗り、半分以上が入る画素を塗ったもの。
// 残りの 6 方向は、この 2 枚を 90 度ずつ時計回りに回す。テストは test/test_icons.cpp
#include <math.h>

static const int ICON_N = 11;

static const char *const ICON_PLANE_UP[ICON_N] = {
  ".....#.....",
  "....###....",
  "....###....",
  "....###....",
  "....###....",
  "...#####...",
  ".#########.",
  "###########",
  "##..###..##",
  "....###....",
  "..#######..",
};

static const char *const ICON_PLANE_UPRIGHT[ICON_N] = {
  "...........",
  ".......##..",
  "......####.",
  "###..#####.",
  "#########..",
  "..######...",
  "..#####....",
  "#######....",
  ".#######...",
  "..##..##...",
  "...#..##...",
};

static const char *const ICON_SHIP[ICON_N] = {
  "...........",
  "...........",
  "......#....",
  ".....##....",
  "...#####...",
  "...#####...",
  "###########",
  ".#########.",
  "..#######..",
  "...........",
  "...........",
};

// 画面の上で (dx, dy) へ進むときの向き (y は下向き)。0 = 上、時計回りに 45 度ずつ 7 まで
static inline int iconDir(float dx, float dy) {
  float a = atan2f(dx, -dy);  // 上が 0、時計回りが正
  int d = (int)lroundf(a / (float)(M_PI / 4));
  return (d % 8 + 8) % 8;
}

// 印の (x, y) を塗るか。ship なら dir は見ない
static inline bool iconPixel(bool ship, int dir, int x, int y) {
  if (x < 0 || y < 0 || x >= ICON_N || y >= ICON_N) return false;
  if (ship) return ICON_SHIP[y][x] == '#';
  dir &= 7;
  for (int k = 0; k < dir / 2; k++) {  // 時計回りに 1 回回した絵の (x, y) は、回す前の (y, N-1-x)
    int t = x;
    x = y;
    y = ICON_N - 1 - t;
  }
  return ((dir & 1) ? ICON_PLANE_UPRIGHT : ICON_PLANE_UP)[y][x] == '#';
}
