// Host test for backlight_cmd.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_backlight_cmd test/test_backlight_cmd.cpp && /tmp/test_backlight_cmd
#include <cassert>
#include <cstdio>
#include "../backlight_cmd.h"

int main() {
  // #b0 / #b1 set it, whatever it was
  assert(backlightAfter(true, '0') == false && backlightAfter(false, '0') == false);
  assert(backlightAfter(true, '1') == true && backlightAfter(false, '1') == true);
  // #b alone (end of line, or nothing more) still toggles, as before
  assert(backlightAfter(true, '\n') == false && backlightAfter(false, '\n') == true);
  assert(backlightAfter(true, -1) == false && backlightAfter(false, -1) == true);
  // only 0 and 1 are arguments
  assert(takesArg('0') && takesArg('1') && !takesArg('2') && !takesArg('\n') && !takesArg(-1));
  puts("test_backlight_cmd: ok");
}
