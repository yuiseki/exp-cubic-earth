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

// 送れたか (ブロードキャストは電波に乗ったか、ユニキャストは相手の ACK が返ったか)
void onSent(const esp_now_send_info_t *info, esp_now_send_status_t st) {
  const uint8_t *m = info->des_addr;
  Serial.printf("delivered %s to %02X:%02X:%02X:%02X:%02X:%02X\n", st == ESP_NOW_SEND_SUCCESS ? "ok" : "FAIL", m[0], m[1], m[2], m[3], m[4], m[5]);
}

// "!AA:BB:CC:DD:EE:FF <行>" はその MAC だけに送る (ユニキャスト、ACK が返る。電波が届いているかの切り分け用)
bool parseMac(const char *p, uint8_t *m) {
  unsigned v[6];
  if (sscanf(p, "%x:%x:%x:%x:%x:%x", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5]) != 6) return false;
  for (int i = 0; i < 6; i++) m[i] = v[i];
  return true;
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
  esp_now_register_send_cb(onSent);
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BROADCAST, 6);
  peer.channel = ESPNOW_CHANNEL;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
  uint8_t m[6];
  esp_wifi_get_mac(WIFI_IF_STA, m);
  uint8_t ch = 0;
  wifi_second_chan_t ch2;
  esp_wifi_get_channel(&ch, &ch2);
  Serial.printf("espnow bridge ready: %02X:%02X:%02X:%02X:%02X:%02X, channel %d (asked %d)\n", m[0], m[1], m[2], m[3], m[4], m[5], ch, ESPNOW_CHANNEL);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (len == 1 && line[0] == '?') {  // 中継自身の状態
        uint8_t ch = 0;
        wifi_second_chan_t ch2;
        esp_wifi_get_channel(&ch, &ch2);
        Serial.printf("bridge: channel %d\n", ch);
        {
        int n = WiFi.scanNetworks();
        Serial.printf("%s %d access points\n", "bridge scan:", n);
        for (int i = 0; i < n && i < 8; i++) Serial.printf("%s   ch %d rssi %d %s\n", "bridge scan:", WiFi.channel(i), WiFi.RSSI(i), WiFi.SSID(i).c_str());
        WiFi.scanDelete();
        esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
      }
        len = 0;
      } else if (len > 19 && line[0] == '!') {
        uint8_t m[6];
        if (parseMac(line + 1, m)) {
          if (!esp_now_is_peer_exist(m)) {
            esp_now_peer_info_t peer = {};
            memcpy(peer.peer_addr, m, 6);
            peer.channel = ESPNOW_CHANNEL;
            esp_now_add_peer(&peer);
          }
          line[len] = '\n';
          bool ok = esp_now_send(m, (const uint8_t *)line + 19, len - 18) == ESP_OK;
          Serial.printf("sent %s (unicast): %.*s\n", ok ? "ok" : "FAIL", len - 19, line + 19);
        }
        len = 0;
      } else if (len) {
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
