#pragma once
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "font5x7.h"

// 起動直後と面の割り当て用 (#N): 白地に黒で、上から ユニット名 (UNIT-01-N)、基板の名前 (基板 0, 1, 2 = A, B, C) を大きく、
// その下に CUBIC-EARTH。四辺の中ほどに辺の番号を描く。辺は上 1、右 2、下 3、左 4 (パネルを表から見て、上から時計回り)。
// 文字はどれもパネルの向きのまま (回転を付けない) なので、文字の上がパネルの上。「A2 と B4 が接している」のように伝える。
// 5x7 フォント (font5x7.h) は英大文字と数字と記号だけなので、小文字は描けない。
// ユニット名は MAC アドレスから決める (unitName)。test/test_face_label.cpp で確かめる
#define FACE_LABEL_SCALE 20        // 中央の文字: 5x7 の 1 ドットを 20 画素四方に (100 x 140)
#define FACE_LABEL_TEXT_SCALE 5    // ユニット名と CUBIC-EARTH
#define FACE_LABEL_EDGE_SCALE 5    // 辺の番号: 25 x 35
#define FACE_LABEL_TB 26           // 上下の辺の番号の中心まで、辺から
#define FACE_LABEL_LR 30           // 左右の辺の番号の中心まで、辺から
#define FACE_LABEL_UNIT_Y 112      // ユニット名の中心の高さ
#define FACE_LABEL_NAME_Y 368      // CUBIC-EARTH の中心の高さ

// (cx, cy) を中心に倍率 s で描いた文字 ch が (x, y) を塗るか
static inline bool glyphInk(char ch, int cx, int cy, int s, int x, int y) {
  int tx = x - (cx - 5 * s / 2), ty = y - (cy - 7 * s / 2);
  if (ch < 32 || ch > 95 || tx < 0 || ty < 0 || tx >= 5 * s || ty >= 7 * s) return false;
  return (FONT5X7[ch - 32][ty / s] >> (4 - tx / s)) & 1;
}

// 文字列 str を、(cx, cy) を中心に、1 文字 6 ドット幅 (文字の幅 5 + 隙間 1) で描いたものが (x, y) を塗るか。小文字は大文字に直す
static inline bool stringInk(const char *str, int cx, int cy, int s, int x, int y) {
  int n = 0;
  while (str[n]) n++;
  int left = cx - (n * 6 * s - s) / 2, ty = y - (cy - 7 * s / 2);
  int k = (x - left) / (6 * s);
  if (x < left || ty < 0 || ty >= 7 * s || k >= n) return false;
  char ch = str[k];
  if (ch >= 'a' && ch <= 'z') ch -= 32;
  int tx = (x - left) - k * 6 * s;
  if (ch < 32 || ch > 95 || tx >= 5 * s) return false;
  return (FONT5X7[ch - 32][ty / s] >> (4 - tx / s)) & 1;
}

static inline uint16_t faceLabelColor(int board, const char *unit, int x, int y, int n = 480) {
  const int S = FACE_LABEL_EDGE_SCALE, c = n / 2;
  bool ink = stringInk(unit, c, FACE_LABEL_UNIT_Y, FACE_LABEL_TEXT_SCALE, x, y) ||
             glyphInk('A' + board, c, c, FACE_LABEL_SCALE, x, y) ||
             stringInk("CUBIC-EARTH", c, FACE_LABEL_NAME_Y, FACE_LABEL_TEXT_SCALE, x, y) ||
             glyphInk('1', c, FACE_LABEL_TB, S, x, y) || glyphInk('2', n - FACE_LABEL_LR, c, S, x, y) ||
             glyphInk('3', c, n - FACE_LABEL_TB, S, x, y) || glyphInk('4', FACE_LABEL_LR, c, S, x, y);
  return ink ? 0x0000 : 0xFFFF;
}

// モジュールの名前 (MAC アドレスから): 北極側 B8:F8:62:F8:DB:A0 は UNIT-01-N、南極側 8C:BF:EA:8F:3F:38 は UNIT-01-S。
// 知らない MAC は末尾 2 バイトで UNIT-ABCD。out の大きさ n に収まらない分は切る
static inline void unitName(const uint8_t mac[6], char *out, size_t n) {
  static const uint8_t NORTH[6] = {0xB8, 0xF8, 0x62, 0xF8, 0xDB, 0xA0}, SOUTH[6] = {0x8C, 0xBF, 0xEA, 0x8F, 0x3F, 0x38};
  char tmp[16];
  if (memcmp(mac, NORTH, 6) == 0) snprintf(tmp, sizeof tmp, "UNIT-01-N");
  else if (memcmp(mac, SOUTH, 6) == 0) snprintf(tmp, sizeof tmp, "UNIT-01-S");
  else snprintf(tmp, sizeof tmp, "UNIT-%02X%02X", mac[4], mac[5]);
  if (n == 0) return;
  snprintf(out, n, "%s", tmp);
}
