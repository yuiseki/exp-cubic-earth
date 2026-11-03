#pragma once
#include <stddef.h>
#include <stdio.h>
#include <string.h>

// #j: Web に置いた JPEG を取ってパネルに描く (lt7680_multi.ino の fetchSides)。ここは Wi-Fi に触らない純粋な部分。
// test/test_web_faces.cpp で確かめる

// <base>/<module>-side-<a|b|c>.jpg (基板 0, 1, 2 = A, B, C)。入りきらないか基板が範囲外なら false
inline bool sideUrl(char *out, size_t n, const char *base, const char *module, int board) {
  if (board < 0 || board > 2) return false;
  size_t bl = strlen(base);
  const char *sep = (bl && base[bl - 1] == '/') ? "" : "/";
  int w = snprintf(out, n, "%s%s%s-side-%c.jpg", base, sep, module, 'a' + board);
  return w > 0 && (size_t)w < n;
}

// モジュール名 (ファイル名の頭、NVS の "name"): 小文字、数字、'-' の 1〜15 文字
inline bool moduleNameOk(const char *s) {
  size_t n = strlen(s);
  if (n < 1 || n > 15) return false;
  for (size_t i = 0; i < n; i++) {
    char c = s[i];
    if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return false;
  }
  return true;
}

// 試す AP の順番を order に入れ、数を返す。secrets.h の並びのうち、スキャンで見えたものを並び順に。
// 1 つも見えなければ全部を並び順に (隠し SSID のことがある)。expt-the-map-runs と同じ考え方
inline int apOrder(const char *const *aps, int nAps, const char *const *seen, int nSeen, int *order) {
  int k = 0;
  for (int a = 0; a < nAps; a++)
    for (int i = 0; i < nSeen; i++)
      if (strcmp(aps[a], seen[i]) == 0) { order[k++] = a; break; }
  if (k == 0)
    for (int a = 0; a < nAps; a++) order[k++] = a;
  return k;
}
