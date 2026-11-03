#pragma once
#include <stdint.h>

// #G の間に、LT7680 のレジスタを読み返して、書いたはずの値と比べる。
// 崩れた面では表示の開始アドレスや透明色が化けていた (2026-11-03) ので、どの基板のどのレジスタがいつ化けるかを記録に残す。
// 化けたのがチップの中か読み出しかを分けるため、違えばもう一度読んで両方を出す。test/test_reg_verify.cpp で確かめる
struct RegExpect { uint8_t reg, want; };
static const int REG_VERIFY_MAX = 64;

// #G で変わらないはずのレジスタ。front は今映しているページの開始アドレス
inline int gExpect(RegExpect *e, uint32_t front) {
  int n = 0;
  for (int i = 0; i < 4; i++) e[n++] = {(uint8_t)(0x20 + i), (uint8_t)(front >> (8 * i))};  // 主画面の開始アドレス
  e[n++] = {0x24, 0xE0}; e[n++] = {0x25, 0x01};  // 主画面の幅 480
  e[n++] = {0x97, 0xE0}; e[n++] = {0x98, 0x01};  // BTE の写し元の幅 480
  e[n++] = {0xAB, 0xE0}; e[n++] = {0xAC, 0x01};  // BTE の写し先の幅 480
  e[n++] = {0xD5, 0xF8}; e[n++] = {0xD6, 0x00}; e[n++] = {0xD7, 0xF8};  // 透明色 0xF81F
  e[n++] = {0x92, 0x25};  // BTE の色の形式
  return n;
}

// regCache が「チップに入っている」と思っている値 (lo〜hi) を足す。キャッシュがあると、化けた値は書き直されない
inline int cacheExpect(RegExpect *e, int n, const int16_t *cache, uint8_t lo, uint8_t hi) {
  for (int r = lo; r <= hi && n < REG_VERIFY_MAX; r++)
    if (cache[r] >= 0) e[n++] = {(uint8_t)r, (uint8_t)cache[r]};
  return n;
}

// 違ったレジスタの数を返す。report(reg, want, got, again)
template <typename R, typename F> int verifyRegs(const RegExpect *e, int n, R read, F report) {
  int bad = 0;
  for (int i = 0; i < n; i++) {
    uint8_t got = read(e[i].reg);
    if (got == e[i].want) continue;
    report(e[i].reg, e[i].want, got, read(e[i].reg));
    bad++;
  }
  return bad;
}
