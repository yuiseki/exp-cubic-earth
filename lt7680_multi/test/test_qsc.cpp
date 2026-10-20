// Host test for qsc.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_qsc test/test_qsc.cpp && /tmp/test_qsc
#include <cassert>
#include <cmath>
#include <cstdio>
#include "../qsc.h"
#include "qsc_golden.h"

int main() {
  QscFaces q;
  qscInit(q, 139.767f, 480);
  double worst = 0;
  for (const auto &g : QSC_GOLDEN) {
    float v[3];
    qscFromLatLon(g.lat, g.lon, v);
    float x, y;
    int f = qscProject(q, v, &x, &y);
    // a point on an edge may land on either face; skip the few within 0.01 px of one
    bool onEdge = g.x < 0.01 || g.x > 479.99 || g.y < 0.01 || g.y > 479.99;
    if (onEdge) continue;
    assert(f == g.face);
    double d = std::fmax(std::fabs(x - g.x), std::fabs(y - g.y));
    worst = std::fmax(worst, d);
  }
  std::printf("qsc ok, worst %.4f px\n", worst);
  assert(worst < 0.05);
}
