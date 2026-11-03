// Host test for idle_backlight.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_idle_backlight test/test_idle_backlight.cpp && /tmp/test_idle_backlight
#include <cassert>
#include <cstdio>
#include "../idle_backlight.h"

int main() {
  const uint32_t MIN = 60000;
  IdleBacklight i;
  i.timeoutMs = 10 * MIN;
  i.activity(0);

  // no host (power bank, exhibition): never off
  assert(!i.off(30 * MIN));

  // host attached: off after the timeout without commands, not before
  i.host(true, 1000);
  assert(!i.off(1000));
  i.host(true, 10 * MIN - 1);
  assert(!i.off(10 * MIN - 1));
  i.host(true, 10 * MIN);
  assert(i.off(10 * MIN));

  // a command turns it back on and restarts the wait
  i.activity(10 * MIN + 5);
  assert(!i.off(10 * MIN + 5));
  i.host(true, 20 * MIN + 5);
  assert(i.off(20 * MIN + 5));

  // a single missed SOF reading does not count as unplugged, but 3 s without the host does
  i.host(false, 20 * MIN + 100);
  assert(i.off(20 * MIN + 100));
  assert(i.off(20 * MIN + 5 + 2999));
  assert(!i.off(20 * MIN + 5 + 3000));  // unplugged from the deck: back on for the exhibition

  // timeout 0: never off
  IdleBacklight never;
  never.timeoutMs = 0;
  never.activity(0);
  never.host(true, 60 * MIN);
  assert(!never.off(60 * MIN));

  // millis() wraps after about 49.7 days
  IdleBacklight w;
  w.timeoutMs = 10 * MIN;
  w.activity(0xFFFFFFFFu - 1000);
  w.host(true, 5000);
  assert(!w.off(5000));
  w.host(true, 10 * MIN);
  assert(w.off(10 * MIN));
  puts("test_idle_backlight: ok");
}
