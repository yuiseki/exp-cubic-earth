#pragma once
#include <stdint.h>

// 何もしていないときにバックライトを消す (#i)。USB の向こうにホスト (pi4-deck、pi5-deck) がいるときだけ消し、
// モバイルバッテリーや AC アダプター (ホストがいない、展示) では決して消さない。書き込みや記録のために
// デッキにつないで放っておくと、キューブ (約 4W) がデッキの電池を食い続けて、デッキが落ちた (2026-11-03)。
// ホストの有無は USB の SOF の有無 (HWCDC::isPlugged)。一瞬だけ取りこぼすことがあるので、最後に見えてから
// HOST_GRACE_MS の間はつながっているとみなす。test/test_idle_backlight.cpp で確かめる
struct IdleBacklight {
  static const uint32_t HOST_GRACE_MS = 3000;
  uint32_t timeoutMs = 0;  // 0: 消さない
  uint32_t lastActivity = 0, lastHost = 0;
  bool hostSeen = false;

  void activity(uint32_t now) { lastActivity = now; }
  void host(bool plugged, uint32_t now) {
    if (plugged) { lastHost = now; hostSeen = true; }
  }
  bool hostConnected(uint32_t now) const { return hostSeen && now - lastHost < HOST_GRACE_MS; }
  // 今、バックライトを消しておくべきか
  bool off(uint32_t now) const { return timeoutMs && hostConnected(now) && now - lastActivity >= timeoutMs; }
};
