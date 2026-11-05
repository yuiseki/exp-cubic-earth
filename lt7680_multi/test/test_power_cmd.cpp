// Host test for power_cmd.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_power_cmd test/test_power_cmd.cpp && /tmp/test_power_cmd
#include <cassert>
#include <cstdio>
#include "../power_cmd.h"

int main() {
  // #z alone (or only whitespace) asks for the current state
  PowerArg a = parsePowerArg("");
  assert(a.ok && a.what == 0);
  a = parsePowerArg(" \r\n");
  assert(a.ok && a.what == 0);
  // each target takes 1 (save power) or 0 (back to normal)
  const char *targets = "wlpc";
  for (const char *t = targets; *t; t++) {
    char s[4] = {*t, '1', 0, 0};
    a = parsePowerArg(s);
    assert(a.ok && a.what == *t && a.on == 1);
    s[1] = '0';
    a = parsePowerArg(s);
    assert(a.ok && a.what == *t && a.on == 0);
  }
  // trailing newline from the serial line is fine
  a = parsePowerArg("l1\r\n");
  assert(a.ok && a.what == 'l' && a.on == 1);
  // unknown target, missing or bad value, extra characters are errors
  assert(!parsePowerArg("x1").ok);
  assert(!parsePowerArg("w").ok);
  assert(!parsePowerArg("w2").ok);
  assert(!parsePowerArg("w10").ok);
  assert(!parsePowerArg("W1").ok);
  puts("test_power_cmd: ok");
}
