// Host test for byte_ring.h:  g++ -std=c++17 -Wall -Wextra -o /tmp/test_byte_ring test/test_byte_ring.cpp && /tmp/test_byte_ring
#include <cassert>
#include <cstdio>
#include <cstring>
#include "../byte_ring.h"

int main() {
  ByteRing<8> r;  // holds 7 bytes
  assert(r.size() == 0 && r.peek() == -1 && r.pop() == -1);
  assert(r.pushAll((const uint8_t *)"#E\n", 3));
  assert(r.size() == 3 && r.peek() == '#');
  assert(r.pop() == '#' && r.pop() == 'E' && r.pop() == '\n' && r.pop() == -1);
  // wraps around
  for (int k = 0; k < 20; k++) {
    assert(r.pushAll((const uint8_t *)"0,4,2\n", 6));
    char got[7] = {};
    for (int i = 0; i < 6; i++) got[i] = (char)r.pop();
    assert(strcmp(got, "0,4,2\n") == 0);
  }
  // a packet that does not fit is dropped whole, not cut
  assert(r.pushAll((const uint8_t *)"abcde", 5));
  assert(!r.pushAll((const uint8_t *)"xyz", 3));
  assert(r.size() == 5);
  puts("test_byte_ring: ok");
}
