#pragma once
// 名前つきのシーン (#v、#w<名前>,<面>)。microSD の /scenes/<名前>/face<f>.bin。数字のシーン (#s<k>) は名前 "k" と同じ場所。
// 名前は小文字・数字・'-' を '/' でつないだもの (例 "shikisai-lst/2025-07-01")。".." や空の区切りは受けない。
// #v<組>,<から>[,<まで>[,<秒>]]: /scenes/<組>/ の下の、名前が日付のコマ (YYYY-MM-DD) のうち範囲に入るものを名前の順に描く。
// <から> と <まで> は YYYY、YYYY-MM、YYYY-MM-DD のどれでもよく、前の部分が合えば入る ("2025-01" は 1 月の 2 コマとも)。
// <まで> を書かなければ <から> と同じ (1 コマ、または 1 か月分を 1 回)、<まで> を書けば <秒> ごとに止めるまで繰り返す。
// テストは test/test_scene_names.cpp
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const int SCENE_NAME_MAX = 63;
static const int VIEW_DEFAULT_SEC = 5;

static inline bool sceneNameOk(const char *s) {
  size_t n = strlen(s);
  if (n == 0 || (int)n > SCENE_NAME_MAX || s[0] == '/' || s[n - 1] == '/') return false;
  for (size_t i = 0; i < n; i++) {
    char c = s[i];
    bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '/';
    if (!ok) return false;
    if (c == '/' && s[i + 1] == '/') return false;
  }
  return strstr(s, "..") == nullptr;
}

static inline bool sceneDirPath(char *out, size_t n, const char *name) {
  if (!sceneNameOk(name)) return false;
  return snprintf(out, n, "/scenes/%s", name) < (int)n;
}

static inline bool sceneFacePath(char *out, size_t n, const char *name, int f) {
  if (!sceneNameOk(name)) return false;
  return snprintf(out, n, "/scenes/%s/face%d.bin", name, f) < (int)n;
}

// frame (YYYY-MM-DD) が from 以上、to 以下か。from と to は前の部分だけでもよい。to が空なら終わりなし
static inline bool frameInRange(const char *frame, const char *from, const char *to) {
  if (strncmp(frame, from, strlen(from)) < 0) return false;
  if (to[0] && strncmp(frame, to, strlen(to)) > 0) return false;
  return true;
}

struct ViewArgs {
  char set[SCENE_NAME_MAX + 1];
  char from[11], to[11];
  int sec;
  bool loop;
};

static inline bool dateLike(const char *s) {
  size_t n = strlen(s);
  if (n < 4 || n > 10) return false;
  for (size_t i = 0; i < n; i++)
    if (!((s[i] >= '0' && s[i] <= '9') || s[i] == '-')) return false;
  return true;
}

// 前後の空白と改行を落として dst (大きさ n) に写す
static inline void trimCopy(char *dst, size_t n, const char *b, const char *e) {
  while (b < e && (*b == ' ' || *b == '\t')) b++;
  while (e > b && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\r' || e[-1] == '\n')) e--;
  size_t k = (size_t)(e - b) < n - 1 ? (size_t)(e - b) : n - 1;
  memcpy(dst, b, k);
  dst[k] = 0;
}

static inline bool parseViewArgs(const char *s, ViewArgs &v) {
  const char *part[4] = {nullptr, nullptr, nullptr, nullptr};
  const char *end[4] = {nullptr, nullptr, nullptr, nullptr};
  int k = 0;
  const char *p = s;
  part[0] = p;
  for (; *p && *p != '\n'; p++) {
    if (*p == ',') {
      end[k] = p;
      if (++k >= 4) return false;
      part[k] = p + 1;
    }
  }
  end[k] = p;
  if (k < 1) return false;
  char sec[12] = "";
  trimCopy(v.set, sizeof v.set, part[0], end[0]);
  trimCopy(v.from, sizeof v.from, part[1], end[1]);
  if (k >= 2) trimCopy(v.to, sizeof v.to, part[2], end[2]);
  else strcpy(v.to, v.from);
  if (k >= 3) trimCopy(sec, sizeof sec, part[3], end[3]);
  v.loop = k >= 2;
  v.sec = sec[0] ? atoi(sec) : VIEW_DEFAULT_SEC;
  if (!sceneNameOk(v.set) || !dateLike(v.from) || !dateLike(v.to)) return false;
  if (v.loop && v.sec < 1) return false;
  return true;
}
