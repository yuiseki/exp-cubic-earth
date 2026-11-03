// espnow_bridge.ino
//
// 四角い地球 大型版: USB シリアルで受けた 1 行を、ESP-NOW で全員 (ブロードキャスト) に送る中継。
// 母艦や pi5-deck などに挿した ESP32 に焼く。受け手は lt7680_multi。
//   送る: "#E\n" のように、lt7680_multi のシリアルに打つのと同じ行を送る (改行まで、最大 250 バイト)
//   返事: "sent ok: <行>" / "sent FAIL: <行>"。ESP-NOW で届いた行は "rx <MAC>: <行>" と出す
// 起動時に secrets.h の AP に lt7680_multi と同じ並びでつなぎ、ESP-NOW をその AP のチャンネルに相乗りさせる
// (expt-the-map-runs と同じ形)。どれにもつながらなければ ESPNOW_CHANNEL (1)

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#if __has_include("secrets.h")
#include "secrets.h"  // WIFI_APS。secrets.h.example を参照 (gitignore 済み)
#endif

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

// lt7680_multi の joinWiFi と同じ: スキャンで見えた AP を並び順に、見えなければ全部を並び順に試す
bool joinWiFi() {
#ifdef WIFI_APS
  struct Ap { const char *ssid, *pass; };
  static const Ap aps[] = WIFI_APS;
  const int nAps = sizeof aps / sizeof aps[0];
  int n = WiFi.scanNetworks();
  bool anySeen = false;
  for (int a = 0; a < nAps; a++)
    for (int i = 0; i < n; i++) anySeen = anySeen || WiFi.SSID(i) == aps[a].ssid;
  for (int a = 0; a < nAps; a++) {
    bool seen = false;
    for (int i = 0; i < n; i++) seen = seen || WiFi.SSID(i) == aps[a].ssid;
    if (anySeen && !seen) continue;
    WiFi.begin(aps[a].ssid, aps[a].pass);
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 8000) delay(100);
    if (WiFi.status() == WL_CONNECTED) {
      WiFi.scanDelete();
      Serial.printf("wifi: %s, channel %d\n", aps[a].ssid, WiFi.channel());
      return true;
    }
    WiFi.disconnect();
  }
  WiFi.scanDelete();
  Serial.println("wifi: no AP from secrets.h joined");
#else
  Serial.println("wifi: no secrets.h (see secrets.h.example)");
#endif
  return false;
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  if (!joinWiFi()) esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) {
    Serial.println("espnow: init failed");
    return;
  }
  esp_now_register_recv_cb(onRecv);
  esp_now_register_send_cb(onSent);
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BROADCAST, 6);
  peer.channel = 0;  // 今のチャンネル (つないだ AP のもの) に相乗り
  peer.encrypt = false;
  esp_now_add_peer(&peer);
  uint8_t m[6];
  esp_wifi_get_mac(WIFI_IF_STA, m);
  uint8_t ch = 0;
  wifi_second_chan_t ch2;
  esp_wifi_get_channel(&ch, &ch2);
  Serial.printf("espnow bridge ready: %02X:%02X:%02X:%02X:%02X:%02X, channel %d (%s)\n", m[0], m[1], m[2], m[3], m[4], m[5], ch, WiFi.status() == WL_CONNECTED ? "the AP's" : "ESPNOW_CHANNEL");
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
        if (WiFi.status() != WL_CONNECTED) esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
      }
        len = 0;
      } else if (len > 19 && line[0] == '!') {
        uint8_t m[6];
        if (parseMac(line + 1, m)) {
          if (!esp_now_is_peer_exist(m)) {
            esp_now_peer_info_t peer = {};
            memcpy(peer.peer_addr, m, 6);
            peer.channel = 0;  // 今のチャンネル (つないだ AP のもの) に相乗り
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
