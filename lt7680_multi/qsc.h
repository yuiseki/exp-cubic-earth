#pragma once
#include <math.h>

// 地球の 6 面 (earth_qsc480x6.h) への QSC 投影 (Calabretta & Greisen 2002、FITS 論文 II の 5.6.2)。
// 面 0〜3 は経度 lon0 + 90k を中心とする側面 (北が上)、4 は北極、5 は南極 (面 0 につながる向き)。
// host/qsc.py をそのまま移したもので、host/test_qsc.py が qsc.py を PROJ の +proj=qsc と突き合わせ、
// test/test_qsc.cpp がこちらを qsc.py と突き合わせる
struct QscFaces {
  float n[6][3], ex[6][3], ey[6][3];  // 面の中心、右、上 (単位ベクトル)
  int size;
};

static inline void qscSet(float *d, float a, float b, float c) { d[0] = a; d[1] = b; d[2] = c; }
static inline float qscDot(const float *a, const float *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

static inline void qscInit(QscFaces &q, float lon0Deg, int size) {
  q.size = size;
  for (int k = 0; k < 4; k++) {
    float l = (lon0Deg + 90.0f * k) * (float)M_PI / 180.0f, c = cosf(l), s = sinf(l);
    qscSet(q.n[k], c, s, 0);
    qscSet(q.ex[k], -s, c, 0);
    qscSet(q.ey[k], 0, 0, 1);
  }
  float l = lon0Deg * (float)M_PI / 180.0f, c = cosf(l), s = sinf(l);
  qscSet(q.n[4], 0, 0, 1);
  qscSet(q.ex[4], -s, c, 0);
  qscSet(q.ey[4], -c, -s, 0);  // 北極: lon0 の経線が下
  qscSet(q.n[5], 0, 0, -1);
  qscSet(q.ex[5], -s, c, 0);
  qscSet(q.ey[5], c, s, 0);  // 南極: lon0 の経線が上
}

static inline void qscFromLatLon(double latDeg, double lonDeg, float *v) {
  double la = latDeg * M_PI / 180.0, lo = lonDeg * M_PI / 180.0;
  qscSet(v, (float)(cos(la) * cos(lo)), (float)(cos(la) * sin(lo)), (float)sin(la));
}

// 主軸方向の半幅単位の座標 a (0〜1) と、もう一方の座標 b
static inline void qscEdge(float zeta, float w, float *a, float *b) {
  float one = 1.0f - zeta;
  if (one < 0) one = 0;  // 面の中心では丸めで負になりうる
  *a = sqrtf(one / (1.0f - 1.0f / sqrtf(2.0f + w * w)));
  *b = *a / 15.0f * (atanf(w) - asinf(w / sqrtf(2.0f * (1.0f + w * w)))) * (180.0f / (float)M_PI);
}

// 単位ベクトル v の点が載る面と、その面の画像での画素座標 (0〜size)
static inline int qscProject(const QscFaces &q, const float *v, float *px, float *py) {
  int f = 0;
  float best = -2;
  for (int k = 0; k < 6; k++) {
    float d = qscDot(v, q.n[k]);
    if (d > best) { best = d; f = k; }
  }
  float zeta = best, xi = qscDot(v, q.ex[f]), eta = qscDot(v, q.ey[f]), a, b, x, y;
  if (fabsf(xi) >= fabsf(eta)) {
    qscEdge(zeta, xi != 0 ? eta / xi : 0, &a, &b);
    float s = xi > 0 ? 1.0f : -1.0f;
    x = s * a;
    y = s * b;
  } else {
    qscEdge(zeta, xi / eta, &a, &b);
    float s = eta > 0 ? 1.0f : -1.0f;
    y = s * a;
    x = s * b;
  }
  *px = (x + 1) / 2 * q.size;
  *py = (1 - y) / 2 * q.size;
  return f;
}
