#pragma once
#include <stddef.h>
#include <stdint.h>

// 1 つの書き手 (ESP-NOW の受信コールバック) と 1 つの読み手 (loop) の間のバイトの輪。N - 1 バイトまで入る。
// 入りきらない塊は丸ごと捨てる (命令の行が途中で切れないように)。test/test_byte_ring.cpp で確かめる
template <size_t N> struct ByteRing {
  uint8_t buf[N];
  volatile size_t head = 0, tail = 0;  // head は書き手だけ、tail は読み手だけが進める
  size_t size() const { return (head + N - tail) % N; }
  bool pushAll(const uint8_t *p, size_t n) {
    if (n > N - 1 - size()) return false;
    size_t h = head;
    for (size_t i = 0; i < n; i++) { buf[h] = p[i]; h = (h + 1) % N; }
    head = h;
    return true;
  }
  int peek() const { return head == tail ? -1 : buf[tail]; }
  int pop() {
    if (head == tail) return -1;
    int c = buf[tail];
    tail = (tail + 1) % N;
    return c;
  }
};
