// Host test for flight_track.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_flight_track test/test_flight_track.cpp && /tmp/test_flight_track
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include "../flight_track.h"

static void put16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = v >> (8 * i); }

int main() {
  // header: "CEF1", keys, step minutes, t0, flights
  uint8_t h[FT_HEADER];
  memcpy(h, "CEF1", 4);
  put16(h + 4, 96); put16(h + 6, 15); put32(h + 8, 1793664000u); put32(h + 12, 3);
  FtHeader fh;
  assert(ftParseHeader(h, sizeof h, FT_HEADER + 3 * (8 + 96 * 4), &fh));
  assert(fh.keys == 96 && fh.stepMin == 15 && fh.t0 == 1793664000u && fh.flights == 3);
  assert(ftRecordBytes(fh) == 8 + 96 * 4);
  assert(ftFileBytes(fh) == FT_HEADER + 3 * (8 + 96 * 4));
  assert(!ftParseHeader(h, sizeof h, ftFileBytes(fh) - 1, &fh));  // truncated download
  h[3] = '2';
  assert(!ftParseHeader(h, sizeof h, FT_HEADER + 3 * (8 + 96 * 4), &fh));             // not this format
  h[3] = '1'; put16(h + 4, 0);
  assert(!ftParseHeader(h, sizeof h, FT_HEADER + 3 * (8 + 96 * 4), &fh));             // no keyframes

  // keyframes in 0.01 degrees, FT_NONE when not airborne
  int16_t k[] = {3500, 13900, 3600, 14000, FT_NONE, FT_NONE, 3700, 17950, 3700, -17950};
  float lat, lon;
  assert(ftPosition(k, 5, 0.5f, &lat, &lon));
  assert(fabsf(lat - 35.5f) < 1e-3 && fabsf(lon - 139.5f) < 1e-3);
  assert(ftPosition(k, 5, 0.0f, &lat, &lon) && fabsf(lat - 35.0f) < 1e-3);
  assert(!ftPosition(k, 5, 1.5f, &lat, &lon));  // next keyframe is on the ground
  assert(!ftPosition(k, 5, 2.5f, &lat, &lon));
  assert(ftPosition(k, 5, 3.5f, &lat, &lon));   // crosses the date line: 179.5 -> -179.5 through 180
  assert(fabsf(lat - 37.0f) < 1e-3 && fabsf(fabsf(lon) - 180.0f) < 1e-3);
  assert(!ftPosition(k, 5, 4.5f, &lat, &lon));  // past the last keyframe
  assert(!ftPosition(k, 5, -0.5f, &lat, &lon));

  // replay clock: a day of keys in dayMs, looping
  assert(fabsf(ftKeyAt(0, 96, 120000) - 0.0f) < 1e-6);
  assert(fabsf(ftKeyAt(60000, 96, 120000) - 48.0f) < 1e-4);
  assert(fabsf(ftKeyAt(120000 + 1250, 96, 120000) - 1.0f) < 1e-4);
  puts("test_flight_track: ok");
}
