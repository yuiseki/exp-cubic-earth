#pragma once

// #z<対象><0|1> 消灯中に何がどれだけ電気を使っているかを、1 つずつ止めて測るための命令の引数。
//   w: 無線の省電力 (WiFi.setSleep)。ESP-NOW を取りこぼすかもしれない
//   l: LT7680 の省電力 (PMU のレジスタ 0xDF)
//   p: 液晶 ST7701S のスリープ (SLPIN / SLPOUT)
//   c: CPU の周波数 (1 で 80MHz、0 で 240MHz)
//   s: 表示をまとめて眠らせる (バックライトを消し、液晶、LT7680 の順に)。0 で逆の順に起こし、バックライトを前に戻す。
//      無線はつけたままなので ESP-NOW の命令で起こせる。眠っている間に #z 以外の命令が来ても先に起こす
// 1 で省電力、0 で元に戻す。#z だけ (空白と改行は無視) なら今の状態を出す (what == 0)。
// test/test_power_cmd.cpp で確かめる
struct PowerArg {
  bool ok;
  char what;
  int on;
};

inline PowerArg parsePowerArg(const char *s) {
  size_t n = 0;
  while (s[n]) n++;
  while (n > 0 && (s[n - 1] == ' ' || s[n - 1] == '\r' || s[n - 1] == '\n' || s[n - 1] == '\t')) n--;
  size_t i = 0;
  while (i < n && (s[i] == ' ' || s[i] == '\t')) i++;
  if (i == n) return {true, 0, 0};
  if (n - i != 2) return {false, 0, 0};
  char w = s[i], v = s[i + 1];
  if (w != 'w' && w != 'l' && w != 'p' && w != 'c' && w != 's') return {false, 0, 0};
  if (v != '0' && v != '1') return {false, 0, 0};
  return {true, w, v - '0'};
}
