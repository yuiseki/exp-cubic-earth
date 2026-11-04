#pragma once
// 本物の飛行機の 1 日 (#t、#J)。microSD の /flights/day.bin、Web では <WEB_BASE>/flights.bin。
// 作り手は flights/pack_flights.py。リトルエンディアン:
//   "CEF1", u16 キーフレーム数, u16 キーフレームの間隔 (分), u32 最初のキーフレームの UNIX 時刻, u32 便の数
//   便ごとに: char 便名[8] (NUL 埋め), キーフレームごとに i16 緯度, i16 経度 (0.01 度。飛んでいなければ FT_NONE)
// モジュールは全球の便を読み、自分の面に載る分だけ描く (どの面に載るかは #G と同じ投影で決める)
#include <stdint.h>
#include <string.h>

static const int FT_HEADER = 16;
static const int16_t FT_NONE = INT16_MIN;

struct FtHeader { uint16_t keys, stepMin; uint32_t t0, flights; };
struct FlightSet { FtHeader h; uint8_t *data; };  // data はファイル全体 (PSRAM)

// microSD 上のファイルと、PSRAM に読んだ中身 (name は Web 上のファイル名 <name>.bin)
struct TrackFile {
  const char *name, *path, *tmp;
  FlightSet set;
};

static inline uint32_t ftRecordBytes(const FtHeader &h) { return 8u + 4u * h.keys; }
static inline uint32_t ftFileBytes(const FtHeader &h) { return FT_HEADER + h.flights * ftRecordBytes(h); }

// 先頭を読み、ファイル全体の長さ size と食い違わないか (途中で切れた取得を弾く) も見る
static inline bool ftParseHeader(const uint8_t *p, uint32_t n, uint32_t size, FtHeader *h) {
  if (n < (uint32_t)FT_HEADER || memcmp(p, "CEF1", 4) != 0) return false;
  h->keys = p[4] | p[5] << 8;
  h->stepMin = p[6] | p[7] << 8;
  h->t0 = (uint32_t)p[8] | (uint32_t)p[9] << 8 | (uint32_t)p[10] << 16 | (uint32_t)p[11] << 24;
  h->flights = (uint32_t)p[12] | (uint32_t)p[13] << 8 | (uint32_t)p[14] << 16 | (uint32_t)p[15] << 24;
  return h->keys > 0 && h->stepMin > 0 && size == ftFileBytes(*h);
}

// キーフレームの列 k (緯度, 経度 の組が keys 個) の、小数のキー位置 t での場所。
// 前後のキーフレームのどちらかで飛んでいなければ false (離陸前、着陸後、記録の途切れ)。
// 間隔 15 分なら 1 区間は 2 度ほどなので、緯度経度のまま直線で補う。経度は日付変更線をまたぐ側で補う
static inline bool ftPosition(const int16_t *k, int keys, float t, float *lat, float *lon) {
  if (t < 0) return false;
  int i = (int)t;
  float f = t - i;
  if (i >= keys) return false;
  if (f == 0.0f) {
    if (k[2 * i] == FT_NONE) return false;
    *lat = k[2 * i] / 100.0f;
    *lon = k[2 * i + 1] / 100.0f;
    return true;
  }
  if (i + 1 >= keys || k[2 * i] == FT_NONE || k[2 * i + 2] == FT_NONE) return false;
  float la0 = k[2 * i] / 100.0f, lo0 = k[2 * i + 1] / 100.0f, la1 = k[2 * i + 2] / 100.0f, lo1 = k[2 * i + 3] / 100.0f;
  if (lo1 - lo0 > 180.0f) lo1 -= 360.0f;
  if (lo0 - lo1 > 180.0f) lo1 += 360.0f;
  *lat = la0 + (la1 - la0) * f;
  float lo = lo0 + (lo1 - lo0) * f;
  if (lo > 180.0f) lo -= 360.0f;
  if (lo < -180.0f) lo += 360.0f;
  *lon = lo;
  return true;
}

// 再生の時計: 1 日 (keys 個) を dayMs ミリ秒で回し、繰り返す
static inline float ftKeyAt(uint32_t ms, int keys, uint32_t dayMs) {
  return (float)(ms % dayMs) * keys / dayMs;
}
