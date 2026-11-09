// Host test for scene_names.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_scene_names test/test_scene_names.cpp && /tmp/test_scene_names
#include <cassert>
#include <cstdio>
#include <cstring>
#include "../scene_names.h"

int main() {
  // names: lower-case letters, digits, '-', and '/' between parts; no "..", no leading or trailing '/'
  assert(sceneNameOk("shikisai-lst"));
  assert(sceneNameOk("shikisai-lst/2025-01-01"));
  assert(sceneNameOk("12"));
  assert(!sceneNameOk(""));
  assert(!sceneNameOk("/abs"));
  assert(!sceneNameOk("a/"));
  assert(!sceneNameOk("a//b"));
  assert(!sceneNameOk("a/../b"));
  assert(!sceneNameOk("Upper"));
  assert(!sceneNameOk("sp ace"));
  char longname[80];
  memset(longname, 'a', sizeof longname - 1);
  longname[sizeof longname - 1] = 0;
  assert(!sceneNameOk(longname));

  // paths: numbered scenes stay where they were
  char p[96];
  assert(sceneFacePath(p, sizeof p, "1", 4) && strcmp(p, "/scenes/1/face4.bin") == 0);
  assert(sceneFacePath(p, sizeof p, "shikisai-lst/2025-07-01", 0) && strcmp(p, "/scenes/shikisai-lst/2025-07-01/face0.bin") == 0);
  assert(!sceneFacePath(p, sizeof p, "../x", 0));
  assert(sceneDirPath(p, sizeof p, "shikisai-lst") && strcmp(p, "/scenes/shikisai-lst") == 0);
  // the name "earth" is the earth every board shows after boot: /earth/face<f>.bin, outside /scenes
  assert(sceneDirPath(p, sizeof p, "earth") && strcmp(p, "/earth") == 0);
  assert(sceneFacePath(p, sizeof p, "earth", 5) && strcmp(p, "/earth/face5.bin") == 0);
  assert(sceneFacePath(p, sizeof p, "earth-2", 5) && strcmp(p, "/scenes/earth-2/face5.bin") == 0);
  assert(sceneFacePath(p, sizeof p, "earth/x", 0) && strcmp(p, "/scenes/earth/x/face0.bin") == 0);

  // range: "2025-01" takes both halves of January, a full date takes that one frame on
  assert(frameInRange("2025-01-01", "2025-01", "2026-10"));
  assert(frameInRange("2025-01-16", "2025-01", "2026-10"));
  assert(frameInRange("2026-10-01", "2025-01", "2026-10"));
  assert(!frameInRange("2024-12-16", "2025-01", "2026-10"));
  assert(!frameInRange("2026-11-01", "2025-01", "2026-10"));
  assert(frameInRange("2025-07-16", "2025-07-16", "2025-07-16"));
  assert(!frameInRange("2025-07-01", "2025-07-16", "2025-07-16"));
  assert(frameInRange("2030-01-01", "2025-01", ""));  // no end: to the last

  // #v arguments: <set>,<from>[,<to>[,<sec>]]
  ViewArgs v;
  assert(parseViewArgs("shikisai-lst,2025-01,2026-10,5", v));
  assert(strcmp(v.set, "shikisai-lst") == 0 && strcmp(v.from, "2025-01") == 0 && strcmp(v.to, "2026-10") == 0 && v.sec == 5);
  assert(v.loop);
  assert(parseViewArgs("shikisai-lst,2025-07-01", v));
  assert(strcmp(v.to, "2025-07-01") == 0 && !v.loop);  // one frame: the start is also the end
  assert(parseViewArgs("shikisai-lst,2025-01,2026-10", v) && v.sec == VIEW_DEFAULT_SEC && v.loop);
  assert(parseViewArgs(" shikisai-lst , 2025-01 \r", v) && strcmp(v.set, "shikisai-lst") == 0 && strcmp(v.from, "2025-01") == 0);
  assert(!parseViewArgs("shikisai-lst", v));
  assert(!parseViewArgs("../x,2025-01", v));
  assert(!parseViewArgs("shikisai-lst,2025-01,2026-10,0", v));  // a loop needs time to show each frame
  assert(!parseViewArgs("shikisai-lst,20x5", v));

  // the half-month a frame name stands for, for the log
  puts("ok");
  return 0;
}
