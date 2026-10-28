#pragma once
#include <stdint.h>
#include "font5x7.h"

// 面の割り当て用 (#N): 白地に黒で、パネルの中央に基板の名前 (基板 0, 1, 2 = A, B, C) を大きく、
// 各辺の中ほどに辺の番号を描く。辺は上 1、右 2、下 3、左 4 (パネルを表から見て、上から時計回り)。
// 文字はどれもパネルの向きのまま (回転を付けない) なので、文字の上がパネルの上。「A2 と B4 が接している」のように伝える。
// test/test_face_label.cpp で確かめる
#define FACE_LABEL_SCALE 40       // 中央の文字: 5x7 の 1 ドットを 40 画素四方に (200 x 280)
#define FACE_LABEL_EDGE_SCALE 12  // 辺の番号: 60 x 84
#define FACE_LABEL_EDGE_INSET 24  // 辺から番号までの隙間

// (cx, cy) を中心に倍率 s で描いた文字 ch が (x, y) を塗るか
static inline bool glyphInk(char ch, int cx, int cy, int s, int x, int y) {
  int tx = x - (cx - 5 * s / 2), ty = y - (cy - 7 * s / 2);
  if (ch < 32 || ch > 95 || tx < 0 || ty < 0 || tx >= 5 * s || ty >= 7 * s) return false;
  return (FONT5X7[ch - 32][ty / s] >> (4 - tx / s)) & 1;
}

static inline uint16_t faceLabelColor(int board, int x, int y, int n = 480) {
  const int S = FACE_LABEL_EDGE_SCALE, c = n / 2, near = FACE_LABEL_EDGE_INSET;
  const int dx = near + 5 * S / 2, dy = near + 7 * S / 2;  // 辺から番号の中心まで (左右の辺は文字の幅、上下は高さで測る)
  bool ink = glyphInk('A' + board, c, c, FACE_LABEL_SCALE, x, y) ||
             glyphInk('1', c, dy, S, x, y) || glyphInk('2', n - dx, c, S, x, y) ||
             glyphInk('3', c, n - dy, S, x, y) || glyphInk('4', dx, c, S, x, y);
  return ink ? 0x0000 : 0xFFFF;
}
