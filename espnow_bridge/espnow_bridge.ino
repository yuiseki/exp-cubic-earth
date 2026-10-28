// espnow_bridge.ino
//
// 四角い地球 大型版: USB シリアルで受けた 1 行を、ESP-NOW で全員 (ブロードキャスト) に送る中継。
// pi5-deck などに挿した ESP32 に焼く。受け手は lt7680_multi (ESPNOW_CHANNEL と同じチャンネル)。
//   送る: "#E\n" のように、lt7680_multi のシリアルに打つのと同じ行を送る (改行まで、最大 250 バイト)
//   返事: "sent ok: <行>" / "sent FAIL: <行>"。ESP-NOW で届いた行は "rx <MAC>: <行>" と出す
// チャンネルは 1 に固定 (Wi-Fi のアクセスポイントにはつながない)

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#ifndef ESPNOW_CHANNEL
#define ESPNOW_CHANNEL 1
#endif

static const uint8_t BROADCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
char line[251];
int len = 0;

void onRecv(const esp_now_recv_info_t *info, const uint8_t *data, int n) {
  const uint8_t *m = info->src_addr;
  Serial.printf("rx %02X:%02X:%02X:%02X:%02X:%02X: %.*s\n", m[0], m[1], m[2], m[3], m[4], m[5], n, (const char *)data);
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) {
    Serial.println("espnow: init failed");
    return;
  }
  esp_now_register_recv_cb(onRecv);
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BROADCAST, 6);
  peer.channel = ESPNOW_CHANNEL;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
  uint8_t m[6];
  esp_wifi_get_mac(WIFI_IF_STA, m);
  Serial.printf("espnow bridge ready: %02X:%02X:%02X:%02X:%02X:%02X, channel %d\n", m[0], m[1], m[2], m[3], m[4], m[5], ESPNOW_CHANNEL);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (len) {
        line[len] = '\n';  // 受け手のシリアルと同じく、改行で行が終わる
        bool ok = esp_now_send(BROADCAST, (const uint8_t *)line, len + 1) == ESP_OK;
        Serial.printf("sent %s: %.*s\n", ok ? "ok" : "FAIL", len, line);
        len = 0;
      }
    } else if (len < 250) {
      line[len++] = c;
    }
  }
  delay(1);
}
