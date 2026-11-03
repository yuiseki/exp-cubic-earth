// Host test for reg_verify.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_reg_verify test/test_reg_verify.cpp && /tmp/test_reg_verify
#include <cassert>
#include <cstdio>
#include <vector>
#include "../reg_verify.h"

struct Report { uint8_t reg, want, got, again; };

int main() {
  // #G's fixed registers for page address 0x1C2000 (page 1 of 480x480x2)
  RegExpect e[REG_VERIFY_MAX];
  int n = gExpect(e, 0x1C2000);
  auto find = [&](uint8_t r) { for (int i = 0; i < n; i++) if (e[i].reg == r) return (int)e[i].want; return -1; };
  assert(find(0x20) == 0x00 && find(0x21) == 0x20 && find(0x22) == 0x1C && find(0x23) == 0x00);  // main image start
  assert(find(0x24) == 0xE0 && find(0x25) == 0x01);  // main image width 480
  assert(find(0x97) == 0xE0 && find(0x98) == 0x01 && find(0xAB) == 0xE0 && find(0xAC) == 0x01);  // BTE widths
  assert(find(0xD5) == 0xF8 && find(0xD6) == 0x00 && find(0xD7) == 0xF8);  // chroma key 0xF81F
  assert(find(0x92) == 0x25);

  // the cache adds what it believes is in the chip
  int16_t cache[256];
  for (int r = 0; r < 256; r++) cache[r] = -1;
  cache[0x99] = 0x10; cache[0xB1] = 0x26;
  int m = cacheExpect(e, n, cache, 0x93, 0xB4);
  assert(m == n + 2 && e[n].reg == 0x99 && e[n].want == 0x10 && e[n + 1].reg == 0xB1);

  // all match: nothing reported
  uint8_t chip[256] = {};
  for (int i = 0; i < m; i++) chip[e[i].reg] = e[i].want;
  std::vector<Report> got;
  auto read = [&](uint8_t r) { return chip[r]; };
  auto report = [&](uint8_t r, uint8_t w, uint8_t g, uint8_t a) { got.push_back({r, w, g, a}); };
  assert(verifyRegs(e, m, read, report) == 0 && got.empty());

  // a register that is wrong in the chip: reported with the second read
  chip[0xD5] = 0x00;
  assert(verifyRegs(e, m, read, report) == 1);
  assert(got.size() == 1 && got[0].reg == 0xD5 && got[0].want == 0xF8 && got[0].got == 0x00 && got[0].again == 0x00);

  // a read that is wrong once (the chip holds the right value): still reported, again shows the right value
  chip[0xD5] = 0xF8;
  got.clear();
  int calls = 0;
  auto flaky = [&](uint8_t r) { return (r == 0x24 && calls++ == 0) ? (uint8_t)0xFF : chip[r]; };
  assert(verifyRegs(e, m, flaky, report) == 1);
  assert(got.size() == 1 && got[0].reg == 0x24 && got[0].got == 0xFF && got[0].again == 0xE0);
  puts("test_reg_verify: ok");
}
