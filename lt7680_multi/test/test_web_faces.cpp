// Host test for web_faces.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_web_faces test/test_web_faces.cpp && /tmp/test_web_faces
#include <cassert>
#include <cstdio>
#include <cstring>
#include "../web_faces.h"

int main() {
  char url[160];
  // <base>/<module>-side-<a|b|c>.jpg, with or without a slash at the end of the base
  assert(sideUrl(url, sizeof url, "https://z.yuiseki.net/static/tmp/cubic-earth", "north", 0));
  assert(strcmp(url, "https://z.yuiseki.net/static/tmp/cubic-earth/north-side-a.jpg") == 0);
  assert(sideUrl(url, sizeof url, "http://h/x/", "south", 2));
  assert(strcmp(url, "http://h/x/south-side-c.jpg") == 0);
  assert(!sideUrl(url, 10, "http://h/x/", "south", 2));  // too long for the buffer
  assert(!sideUrl(url, sizeof url, "http://h", "south", 3));  // only boards 0-2

  // module names: lower-case letters, digits and '-', 1-15 characters
  assert(moduleNameOk("north") && moduleNameOk("south") && moduleNameOk("m-2"));
  assert(!moduleNameOk("") && !moduleNameOk("North") && !moduleNameOk("a/b") && !moduleNameOk("0123456789abcdef"));

  // APs to try: the visible ones in list order; none visible -> all of them (a hidden SSID)
  const char *aps[] = {"home", "phone", "venue"};
  int order[3];
  const char *seen1[] = {"other", "phone", "home"};
  assert(apOrder(aps, 3, seen1, 3, order) == 2 && order[0] == 0 && order[1] == 1);
  const char *seen2[] = {"venue"};
  assert(apOrder(aps, 3, seen2, 1, order) == 1 && order[0] == 2);
  assert(apOrder(aps, 3, nullptr, 0, order) == 3 && order[0] == 0 && order[2] == 2);
  puts("test_web_faces: ok");
}
