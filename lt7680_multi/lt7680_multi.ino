// lt7680_multi.ino
//
// 四角い地球 大型版: 複数の ER-PCBA5981-1 (LT7680A-R) + ER-TFT040-3 (ST7701S) を 1 台の XIAO ESP32-S3 から
// 駆動するための基板選択の抽象。配線は 2 通り:
//   BOARD_SELECT_DIRECT: 構成 1 (直結で 1 枚)。LCM_SCS を D0、LCD_CS を D2 に直結 (lt7680_earth と同じ配線)
//   既定 (74HC138):      構成 2 (2 枚は -DNUM_BOARDS=2)。アドレス 3 本 (D0, D2, D6) を 74HC138 の A0..A2 に。Y0..Y2 = 基板 0..2 の LCM_SCS、
//                        Y3..Y5 = 基板 0..2 の LCD_CS、Y7 = どれも選ばない。出力は負論理なので CS に直結
// 共有線: LCM_SDI/SDO/SCLK (D10/D9/D8)、LCD_DIN/LCD_SCLK (D5/D4)、LCM_RESET (D1)、BL (D3)
// LCM_SDO (MISO) の共有は、非選択の LT7680 が SDO をハイインピーダンスにする場合だけ成立する (2 枚では成立を確認)
//
// 命令 (先頭に '#'): n<0-2> 基板を選ぶ、0 選んだ基板の流れ、A 全基板の流れ、E 地球、s<k> microSD のシーン k、N 全基板に白地の名前 (基板 0〜2 = A〜C) と辺の番号 (上から時計回りに 1〜4)、K/W 黒/白、r 状態、b バックライト、i<分> 何もしないときにバックライトを消すまでの分 (USB ホストにつながっているときだけ、0 で消さない)
// 面の割り当て (先頭の '#' は無くてよい): x,n[,r] で基板 x に面 n (0-5) を、時計回りに 90 度 x r (0-3) 回して描く。不揮発領域に保存し、再起動後も使う

#include "earth_qsc480x6.h"
#include "rotate.h"
#include "qsc.h"
#include "font5x7.h"
#include "face_label.h"
#include "mover.h"  // (構造体は .ino に書くと Arduino の自動プロトタイプより後ろになる)
#include <Preferences.h>
#include <SPI.h>
#include <SD.h>
#include "soc/gpio_reg.h"
#include "driver/gpio.h"
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "byte_ring.h"
#include "reg_verify.h"
#include "idle_backlight.h"

#ifndef NUM_BOARDS
#define NUM_BOARDS 1
#endif

// QSC の面: 0〜3 は側面 (面 0 は東京 139.767 度を中心に、経度 90 度おきに東へ)、4 は北極、5 は南極。
// 立方体の外から見て、面 k+1 は面 k の右隣、北極は面 0 の上、南極は面 0 の下につながる
#define NUM_FACES 6
// 基板ごとの面。既定は基板 b に側面 b、x,n 命令で変えて不揮発領域 ("cube" の "f<b>") に保存する
int faceOf[NUM_BOARDS];
// 基板ごとの回転 (時計回りに 90 度 x r、パネルを表から見て)。x,n,r 命令で変えて "r<b>" に保存する
int rotOf[NUM_BOARDS];
QscFaces qsc;  // 地球の面への投影 (setup で初期化)
bool windowFull = true;  // 作業ウィンドウが全面か。drawRegion は狭めたままにし、fillRect の前に戻す
Preferences prefs;
// (関数にすると Arduino の自動プロトタイプがここに入り、後ろの enum より前に来てビルドが壊れる)
#define boardFace(b) (faceImage(faceOf[b]))
// 送られてきた面の画像 (#U、PSRAM)。無ければ焼き込みの地球
uint16_t *faceOverride[NUM_FACES];
#define faceImage(f) (faceOverride[f] ? (const uint16_t *)faceOverride[f] : EARTH_QSC480X6[f])

static const int PIN_RESET  = D1;
static const int PIN_BL     = D3;
static const int PIN_SCK    = D8;
static const int PIN_MISO   = D9;
static const int PIN_MOSI   = D10;
static const int PIN_PANEL_SCK = D4;  // CON1 19 LCD_SCLK
static const int PIN_PANEL_SDA = D5;  // CON1 18 LCD_DIN
#ifdef BOARD_SELECT_DIRECT
static const int PIN_SCS    = D0;
static const int PIN_LCD_CS = D2;
#else
static const int PIN_ADDR[3] = {D0, D2, D6};  // 74HC138 の A0, A1, A2
#endif

// ---- 基板の選択 ----
enum Sel { SEL_NONE, SEL_LT, SEL_LCD };
int curBoard = 0;  // 今の命令の対象

#ifndef BOARD_SELECT_DIRECT
uint32_t selMask[8][2][2];  // 番地ごとに [0 にするビット / 1 にするビット][GPIO 0〜31 / 32〜]
#endif

// 74HC138 のアドレスを置く。アドレスを変える瞬間に隣の出力が ns 単位で落ちることがあるが、
// クロックが止まっている間の CS のパルスは LT7680 も ST7701S も無視する
void selectLine(Sel s) {
#ifdef BOARD_SELECT_DIRECT
  digitalWrite(PIN_SCS, s == SEL_LT ? LOW : HIGH);
  digitalWrite(PIN_LCD_CS, s == SEL_LCD ? LOW : HIGH);
#else
  // 3 本を GPIO のレジスタで書く (digitalWrite を 3 回より速い)。先に 0 にするビットを落としてから 1 を立てるので、
  // 7 (どれも選ばない) との行き来では途中に別の番地を通らない
  int code = (s == SEL_NONE) ? 7 : (s == SEL_LT ? curBoard : 3 + curBoard);
  REG_WRITE(GPIO_OUT_W1TC_REG, selMask[code][0][0]);
  REG_WRITE(GPIO_OUT1_W1TC_REG, selMask[code][0][1]);
  REG_WRITE(GPIO_OUT_W1TS_REG, selMask[code][1][0]);
  REG_WRITE(GPIO_OUT1_W1TS_REG, selMask[code][1][1]);
#endif
}

void selectSetup() {
#ifdef BOARD_SELECT_DIRECT
  pinMode(PIN_SCS, OUTPUT);
  pinMode(PIN_LCD_CS, OUTPUT);
#else
  for (int i = 0; i < 3; i++) pinMode(PIN_ADDR[i], OUTPUT);
  for (int code = 0; code < 8; code++)
    for (int i = 0; i < 3; i++) {
      int pin = PIN_ADDR[i], bit = (code >> i) & 1;
      selMask[code][bit][pin >= 32] |= 1u << (pin & 31);
    }
#endif
  selectLine(SEL_NONE);
}

uint32_t regHz = 1000000;  // レジスタの読み書きの速さ。#L<kHz> で変える

// ---- LT7680 (4 線 SPI、1 回 16 クロック、先頭 8 ビットが前置き) ----

// SPI を握ったままにしている間 (RegBurst) は、1 回ごとに取り直さない
bool regHeld = false;

uint8_t xfer16(uint8_t prefix, uint8_t data) {
  if (!regHeld) SPI.beginTransaction(SPISettings(regHz, MSBFIRST, SPI_MODE3));
  selectLine(SEL_LT);
  uint8_t r = SPI.transfer16(((uint16_t)prefix << 8) | data) & 0xFF;
  selectLine(SEL_NONE);
  if (!regHeld) SPI.endTransaction();
  return r;
}

void writeReg(uint8_t reg, uint8_t val) {
  xfer16(0x00, reg);
  xfer16(0x80, val);
}

// 前に書いた値と同じなら書かない writeReg (BTE の位置や大きさのように、毎回少しだけ変わるレジスタ用)。
// 基板ごとに覚える。regCacheClear() で忘れる (初期化し直したあとなど)
int16_t regCache[NUM_BOARDS][256];
void regCacheClear() {
  for (int b = 0; b < NUM_BOARDS; b++)
    for (int r = 0; r < 256; r++) regCache[b][r] = -1;
}
void writeRegC(uint8_t reg, uint8_t val) {
  if (regCache[curBoard][reg] == val) return;
  writeReg(reg, val);
  regCache[curBoard][reg] = val;
}
void writeReg16C(uint8_t reg, uint16_t v) {
  writeRegC(reg, v & 0xFF);
  writeRegC(reg + 1, v >> 8);
}
void writeReg32C(uint8_t reg, uint32_t v) {
  for (int i = 0; i < 4; i++) writeRegC(reg + i, (v >> (8 * i)) & 0xFF);
}

uint8_t readReg(uint8_t reg) {
  xfer16(0x00, reg);
  return xfer16(0xC0, 0x00);
}

uint8_t readStatus() { return xfer16(0x40, 0x00); }

bool waitFor(const char *what, uint32_t timeoutMs, bool (*cond)()) {
  uint32_t t0 = millis();
  while (!cond()) {
    if (millis() - t0 > timeoutMs) {
      Serial.printf("TIMEOUT waiting for %s (board %d)\n", what, curBoard);
      return false;
    }
    delay(1);
  }
  if (millis() - t0 > 100) Serial.printf("waited %lu ms for %s (board %d)\n", (unsigned long)(millis() - t0), what, curBoard);
  return true;
}

// ---- ST7701S (3 線 SPI、9 ビット: 先頭 1 ビットが 0=コマンド / 1=データ) ----
// SCK と MOSI は LT7680 と共有しているので、送る間だけ SPI から外して手で信号を作る

// LCD_init.h と同じく、CLK を Low にしてからデータを置き、High で取り込ませる。CLK は High で待つ
void panelBit(int b) {
  digitalWrite(PIN_PANEL_SCK, LOW);
  digitalWrite(PIN_PANEL_SDA, b);
  delayMicroseconds(1);
  digitalWrite(PIN_PANEL_SCK, HIGH);
  delayMicroseconds(1);
}

// 1 語 (9 ビット) ごとに CS を上げ下げする (LCD_init.h と同じ)
void panelWord(int dc, uint8_t v) {
  selectLine(SEL_LCD);
  panelBit(dc);
  for (int i = 7; i >= 0; i--) panelBit((v >> i) & 1);
  selectLine(SEL_NONE);
}

void panelCmd(uint8_t cmd, const uint8_t *data = nullptr, size_t n = 0) {
  panelWord(0, cmd);
  for (size_t i = 0; i < n; i++) panelWord(1, data[i]);
}

// ER-TFT040-3 の ST7701S 初期化列 (LCD_init.h から変換)。
// 書式: コマンド, データ長, データ...。データ長 0xFE は「待ちだけ」で、次の 1 バイトが ms
static const uint8_t ST7701S_ER_TFT040_3[] = {
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x13,
  0xEF, 1, 0x08,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x10,
  0xC0, 2, 0x3B, 0x00,
  0xC1, 2, 0x0D, 0x02,
  0xC2, 2, 0x21, 0x08,
  0xCD, 1, 0x08,
  0xB0, 16, 0x00, 0x11, 0x18, 0x0E, 0x11, 0x06, 0x07, 0x08, 0x07, 0x22, 0x04, 0x12, 0x0F, 0xAA, 0x31, 0x18,
  0xB1, 16, 0x00, 0x11, 0x19, 0x0E, 0x12, 0x07, 0x08, 0x08, 0x08, 0x22, 0x04, 0x11, 0x11, 0xA9, 0x32, 0x18,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x11,
  0xB0, 1, 0x60,
  0xB1, 1, 0x30,
  0xB2, 1, 0x87,
  0xB3, 1, 0x80,
  0xB5, 1, 0x49,
  0xB7, 1, 0x85,
  0xB8, 1, 0x21,
  0xC1, 1, 0x78,
  0xC2, 1, 0x78,
  0x00, 0xFE, 20,  // 待ち 20 ms
  0xE0, 3, 0x00, 0x1B, 0x02,
  0xE1, 11, 0x08, 0xA0, 0x00, 0x00, 0x07, 0xA0, 0x00, 0x00, 0x00, 0x44, 0x44,
  0xE2, 12, 0x11, 0x11, 0x44, 0x44, 0xED, 0xA0, 0x00, 0x00, 0xEC, 0xA0, 0x00, 0x00,
  0xE3, 4, 0x00, 0x00, 0x11, 0x11,
  0xE4, 2, 0x44, 0x44,
  0xE5, 16, 0x0A, 0xE9, 0xD8, 0xA0, 0x0C, 0xEB, 0xD8, 0xA0, 0x0E, 0xED, 0xD8, 0xA0, 0x10, 0xEF, 0xD8, 0xA0,
  0xE6, 4, 0x00, 0x00, 0x11, 0x11,
  0xE7, 2, 0x44, 0x44,
  0xE8, 16, 0x09, 0xE8, 0xD8, 0xA0, 0x0B, 0xEA, 0xD8, 0xA0, 0x0D, 0xEC, 0xD8, 0xA0, 0x0F, 0xEE, 0xD8, 0xA0,
  0xEB, 7, 0x02, 0x00, 0xE4, 0xE4, 0x88, 0x00, 0x40,
  0xEC, 2, 0x3C, 0x00,
  0xED, 16, 0xAB, 0x89, 0x76, 0x54, 0x02, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x20, 0x45, 0x67, 0x98, 0xBA,
  0xEF, 6, 0x10, 0x0D, 0x04, 0x08, 0x3F, 0x1F,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x00,
  0x3A, 1, 0x66,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x13,
  0xE8, 2, 0x00, 0x0E,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x00,
  0x11, 0,
  0x00, 0xFE, 120,  // 待ち 120 ms
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x13,
  0xE8, 2, 0x00, 0x0C,
  0x00, 0xFE, 10,  // 待ち 10 ms
  0xE8, 2, 0x00, 0x00,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x00,
  0x36, 1, 0x00,
  0x3A, 1, 0x66,
  0x21, 0,
  0x29, 0,
  0x00, 0xFE, 20,  // 待ち 20 ms
};

void resetAndInitPanel();

void sendPanelInit() {
  size_t i = 0;
  while (i < sizeof(ST7701S_ER_TFT040_3)) {
    uint8_t cmd = ST7701S_ER_TFT040_3[i++];
    uint8_t n = ST7701S_ER_TFT040_3[i++];
    if (n == 0xFE) {
      delay(ST7701S_ER_TFT040_3[i++]);
    } else {
      panelCmd(cmd, &ST7701S_ER_TFT040_3[i], n);
      i += n;
    }
  }
}

void initPanel() {
  pinMode(PIN_PANEL_SCK, OUTPUT);
  pinMode(PIN_PANEL_SDA, OUTPUT);
  digitalWrite(PIN_PANEL_SCK, LOW);
  digitalWrite(PIN_PANEL_SDA, LOW);
  sendPanelInit();
  Serial.println("panel: ER-TFT040-3 ST7701S init sent");
}

void resetAndInitPanel() {
  pinMode(PIN_PANEL_SCK, OUTPUT);
  pinMode(PIN_PANEL_SDA, OUTPUT);
  digitalWrite(PIN_PANEL_SCK, LOW);
  digitalWrite(PIN_PANEL_SDA, LOW);
  const uint8_t page0[] = {0x77, 0x01, 0x00, 0x00, 0x00};
  panelCmd(0xFF, page0, sizeof(page0));
  panelCmd(0x01);  // SWRESET
  delay(120);
  sendPanelInit();
}

// ---- 表示タイミング (480x480) ----
static const int HBP = 20, HFP = 20, HPW = 20;  // LCD.h の LCD_HBPD/HFPD/HSPW
static const int VBP = 20, VFP = 12, VPW = 3;   // LCD.h の LCD_VBPD/VFPD/VSPW

// 切り分け: 起動時に LT7680 をリセットに保つ時間。焼き直し (数秒ダウンロードモードに留まる) の後は映り、
// 短いリセットの後は黒かった。リセット中は LT7680 からパネルへの RGB 信号が止まる
#ifndef LT_RESET_HOLD_MS
#define LT_RESET_HOLD_MS 100
#endif

#ifndef SDRAM_ITV
#define SDRAM_ITV 486
#endif

#ifndef LT_RAM_READY_TIMEOUT_MS
#define LT_RAM_READY_TIMEOUT_MS 1000
#endif

#ifndef SDRAM_E0
#define SDRAM_E0 0x29  // データシートの LT7680A-R の値 (4 バンク x 4K 行 x 512 列 = 16MB)
#endif

bool initLt7680NoReset() {
  if (!waitFor("normal operation", 1000, [] { return (readStatus() & 0x02) == 0; })) return false;

  // PLL: LCD.cpp の PLL_Initial と同じ (OD のビット値 2 = 3 分周、R=5)
  writeReg(0x05, (2 << 6) | (5 << 1) | ((20 >> 8) & 1));
  writeReg(0x07, (2 << 6) | (5 << 1) | ((100 >> 8) & 1));
  writeReg(0x09, (2 << 6) | (5 << 1) | ((100 >> 8) & 1));
  writeReg(0x06, 20);
  writeReg(0x08, 100);
  writeReg(0x0A, 100);
  writeReg(0x00, 0x80);  // PLL の設定を反映させる。反映前の読み出しは古い値を返す
  delay(10);
  if (!waitFor("PLL ready", 1000, [] { return (readReg(0x01) & 0x80) != 0; })) return false;

  writeReg(0xE4, 0x04);
  writeReg(0xE0, SDRAM_E0);
  writeReg(0xE1, 0x03);
  // SDRAM のリフレッシュ間隔。LCD.cpp の SDRAM_initail と同じ (64ms / 8192 行 / (1000/60) - 2 = 486)。
  // 以前の 0x61A (1562) では、書いた画素が数十秒で 1 ビットずつ化けていった
  writeReg(0xE2, SDRAM_ITV & 0xFF);
  writeReg(0xE3, SDRAM_ITV >> 8);
  writeReg(0xE4, 0x05);
  if (!waitFor("display RAM ready", LT_RAM_READY_TIMEOUT_MS, [] { return (readStatus() & 0x04) != 0; })) return false;

  // パネルの信号
  writeReg(0x10, 0x04);  // 主画面 16bpp、Sync モード (VSYNC、HSYNC、DE を全部出す)
  writeReg(0x13, 0x00);  // HSYNC と VSYNC は Low アクティブ、DE は High アクティブ
  writeReg(0x14, 480 / 8 - 1);
  writeReg(0x15, 0);
  writeReg(0x16, HBP / 8 - 1);
  writeReg(0x17, HBP % 8);
  writeReg(0x18, HFP / 8 - 1);
  writeReg(0x19, HPW / 8 - 1);
  writeReg(0x1A, (480 - 1) & 0xFF);
  writeReg(0x1B, (480 - 1) >> 8);
  writeReg(0x1C, (VBP - 1) & 0xFF);
  writeReg(0x1D, (VBP - 1) >> 8);
  writeReg(0x1E, VFP - 1);
  writeReg(0x1F, VPW - 1);
  writeReg(0x12, 0x20);  // カラーバー。表示オンはパネルの初期化の後 (デモと同じ順番)
  return true;
}

// ---- 表示用メモリと描画 ----

void writeReg16(uint8_t reg, uint16_t v) {
  writeReg(reg, v & 0xFF);
  writeReg(reg + 1, v >> 8);
}

void writeReg32(uint8_t reg, uint32_t v) {
  for (int i = 0; i < 4; i++) writeReg(reg + i, (v >> (8 * i)) & 0xFF);
}

void setupMemory() {
  writeReg(0x12, readReg(0x12) & ~0x20);                // カラーバーを切る
  writeReg(0x02, (readReg(0x02) & ~0x80 & ~0x06) | 0x40);  // 16 ビットで書く、左から右・上から下
  writeReg(0x03, readReg(0x03) & ~0x07);                // 図形モード、書き込み先は SDRAM
  writeReg(0x10, (readReg(0x10) & ~0x08) | 0x04);       // 主画面は 16bpp
  writeReg32(0x20, 0);                                  // 主画面の開始アドレス
  writeReg16(0x24, 480);                                // 主画面の幅
  writeReg16(0x26, 0);                                  // 主画面の表示の左上 X
  writeReg16(0x28, 0);                                  //                  Y
  writeReg32(0x50, 0);                                  // キャンバスの開始アドレス
  writeReg16(0x54, 480);                                // キャンバスの幅
  writeReg16(0x56, 0);                                  // 作業ウィンドウの左上 X
  writeReg16(0x58, 0);                                  //                    Y
  writeReg16(0x5A, 480);                                // 作業ウィンドウの幅
  writeReg16(0x5C, 480);                                //                高さ
  writeReg(0x5E, (readReg(0x5E) & ~0x06) | 0x01);       // XY 指定、16bpp
}

void waitDrawDone() {
  uint32_t t0 = millis();
  while (readStatus() & 0x08) {
    if (millis() - t0 > 1000) { Serial.println("TIMEOUT waiting for draw"); return; }
  }
}

// RGB565 の色で、(x1,y1)-(x2,y2) の四角形を塗りつぶす (LCD.cpp の DrawSquare_Fill と同じ)
void fillRect(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t color) {
  windowFull = false;  // どの基板の窓が狭いままか覚えていないので、毎回戻す
  fullWindow();
  writeReg(0xD2, color >> 8);
  writeReg(0xD3, color >> 3);
  writeReg(0xD4, color << 3);
  writeReg16(0x68, x1);
  writeReg16(0x6A, y1);
  writeReg16(0x6C, x2);
  writeReg16(0x6E, y2);
  writeReg(0x76, 0xE0);  // 四角形を塗りつぶしで描く
  waitDrawDone();
}

// ---- 地球 ----
#ifndef PIXEL_SPI_HZ
#define PIXEL_SPI_HZ 20000000  // 画素のバーストだけの速さ (480x480 で 588ms)。レジスタの読み書きは 1MHz のまま
#endif
uint32_t pixelHz = PIXEL_SPI_HZ;  // 命令 #S<MHz> で変えられる
// LT7680 の SPI の SCK と MOSI の出力の強さ (ESP32-S3 の GPIO_DRIVE_CAP 0〜3)。hub3 では、XIAO に一番近い J1 (基板 0) だけ、
// 既定の 2 で 20MHz の画素が 1 ビットずれて大きく化けた (描くたびに 10 万画素前後)。1 と 3 では 3 枚とも 0 画素、0 は数十画素
// (#V で読み返して数えた、2026-10-28)。強さの順に良くならず、仕組みは確かめていない。命令 #H<0-3> で変えられる。
// 2026-11-03、モジュール 2 で #G を続けると面が崩れた (電源を替えても崩れた)。#G の間のレジスタの読み返し (reg_verify.h) で、
// 出力 1 ではレジスタ 10MHz で数秒のうちに 1〜2 枚のレジスタが化け (透明色、BTE の幅)、BTE が止まった。
// 出力 3 では 10 分 549 回の読み返しで 3 枚とも 0 回、0 は全滅。それで既定を 3 にした (docs/STATUS.md)
#ifndef SPI_DRIVE
#define SPI_DRIVE 3
#endif
void setSpiDrive(int cap) {
  gpio_set_drive_capability((gpio_num_t)PIN_SCK, (gpio_drive_cap_t)cap);
  gpio_set_drive_capability((gpio_num_t)PIN_MOSI, (gpio_drive_cap_t)cap);
}

// 選んだ基板の表示用メモリの (x0, y0) から w x h の四角形に、face の同じ場所 (基板の回転込み) を書く。
// 64 バイトのバーストで、バーストごとに書き込み FIFO の空きを待つ。書けたら true
bool drawRegion(const uint16_t *face, int x0, int y0, int w, int h) { return drawRegionOver(face, x0, y0, w, h, nullptr, 0); }

// drawRegion と同じだが、ms[0..nm) のうち選んだ基板にある印を、面の画像に重ねて一緒に書く。
// 消すと描くが 1 回の書き込みになるので、途中の (印が消えた) 状態が画面に出ない
bool drawRegionOver(const uint16_t *face, int x0, int y0, int w, int h, const Mover *ms, int nm) {
  writeReg16(0x56, x0);
  writeReg16(0x58, y0);
  writeReg16(0x5A, w);
  writeReg16(0x5C, h);
  writeReg16(0x5F, x0);
  writeReg16(0x61, y0);
  xfer16(0x00, 0x04);
  SPISettings fast(pixelHz, MSBFIRST, SPI_MODE3);
  uint8_t buf[64];
  int n = 0;
  int rot = rotOf[curBoard];
  uint32_t count = (uint32_t)w * h;
  // 重ねる印は、選んだ基板にあって四角に掛かるものだけに先に絞る (画素ごとに全部を調べると重い)
  const Mover *hit[64];
  int nh = 0;
  for (int j = 0; j < nm && nh < 64; j++)
    if (ms[j].board == curBoard && ms[j].bx < x0 + w && ms[j].bx + ms[j].bw > x0 && ms[j].by < y0 + h && ms[j].by + ms[j].bh > y0) hit[nh++] = &ms[j];
  for (uint32_t i = 0; i < count; i++) {
    int x = x0 + i % w, y = y0 + i / w;
    uint16_t c = face[rotatedIndex(x, y, rot)];
    for (int j = 0; j < nh; j++) {
      int mc = moverColorAt(*hit[j], x, y);
      if (mc >= 0) c = mc;
    }
    buf[n++] = c & 0xFF;
    buf[n++] = c >> 8;
    if (n == sizeof(buf) || i == count - 1) {
      // つないでいない基板では MISO が浮き、この状態の読みが 1 のままになりうる。待ち切りにしない
      uint32_t w0 = millis();
      while (readStatus() & 0x80) {
        if (millis() - w0 > 100) {
          Serial.printf("TIMEOUT waiting for write FIFO (board %d)\n", curBoard);
          return false;
        }
      }
      SPI.beginTransaction(fast);
      selectLine(SEL_LT);
      SPI.transfer(0x80);
      SPI.writeBytes(buf, n);
      selectLine(SEL_NONE);
      SPI.endTransaction();
      n = 0;
    }
  }
  windowFull = w == 480 && h == 480;
  return true;
}

// 図形の描画は作業ウィンドウの中に限られるので、四角を塗る前に全面に戻す (drawRegion は窓を狭めたままにする)
void fullWindow() {
  if (windowFull) return;
  writeReg16(0x56, 0);
  writeReg16(0x58, 0);
  writeReg16(0x5A, 480);
  writeReg16(0x5C, 480);
  windowFull = true;
}

// 選んだ基板の表示用メモリに face を書く (480x480 で約 0.6 秒、画素 20MHz)
void drawFace(const uint16_t *face) {
  uint32_t t0 = millis();
  if (drawRegion(face, 0, 0, 480, 480)) Serial.printf("board %d: face written in %lu ms\n", curBoard, (unsigned long)(millis() - t0));
}

// ---- 面の画像を受け取る (#U<面>) ----
// 母艦の host/clouds.py が作る face<k>.bin (480x480、RGB565 リトルエンディアン、面の画像の並び) を host/send_faces.py が送る。
// 4096 バイトずつ受け、受けるたびに "k" を返す (返事を待たずに流すと受信バッファが溢れる)。PSRAM に置き、
// 以後その面は焼き込みの地球の代わりにこれを使う (#D、#G も)。その面を映している基板は描き直す。#u で焼き込みに戻す
void receiveFace(int f) {
  const uint32_t total = 480u * 480u * 2u, chunk = 4096;
  if (f < 0 || f >= NUM_FACES) { Serial.println("U error: face must be 0-5"); return; }
  if (!faceOverride[f]) faceOverride[f] = (uint16_t *)ps_malloc(total);
  if (!faceOverride[f]) { Serial.println("U error: no PSRAM"); return; }
  uint8_t *dst = (uint8_t *)faceOverride[f];
  while (Serial.available()) Serial.read();  // 命令の後ろの改行など
  Serial.println("U ready");
  uint32_t got = 0, t0 = millis();
  while (got < total) {
    uint32_t want = min(chunk, total - got), n = 0, last = millis();
    while (n < want) {
      int a = Serial.available();
      if (a > 0) { n += Serial.readBytes(dst + got + n, min((uint32_t)a, want - n)); last = millis(); }
      else if (millis() - last > 3000) { Serial.printf("U error: timeout at %lu\n", (unsigned long)(got + n)); free(faceOverride[f]); faceOverride[f] = nullptr; return; }
    }
    got += n;
    Serial.print("k");
  }
  Serial.printf("\nU received face %d in %lu ms\n", f, (unsigned long)(millis() - t0));
  int keep = curBoard;
  for (int b = 0; b < NUM_BOARDS; b++)
    if (faceOf[b] == f) { curBoard = b; drawToPage(0); showPage(0); drawFace(boardFace(b)); }
  curBoard = keep;
  Serial.printf("U done %d\n", f);
}

// 表示用メモリがどこまで別々に使えるかを確かめる (#Z、選んだ基板): 512KB ごとの境目 0〜31 (0〜15.5MB) の先頭の
// 1 画素に固有の値を順に書き、全部書いてから読み返す。ある番地が手前の番地と同じ場所を指していれば (折り返し)、
// 先に書いた値が後から書いた値で上書きされて読める。境目どうしで比べるので、折り返しの幅が 512KB の倍数なら必ず見つかる
void probePages() {
  const int N = 32;
  auto at = [](int slot) {
    writeReg32(0x50, (uint32_t)slot * 0x80000);
    writeReg16(0x56, 0); writeReg16(0x58, 0); writeReg16(0x5A, 480); writeReg16(0x5C, 480);
    writeReg16(0x5F, 0); writeReg16(0x61, 0);
    windowFull = true;
    xfer16(0x00, 0x04);
  };
  for (int p = 0; p < N; p++) {
    uint16_t v = 0x1000 + p * 37;
    at(p);
    xfer16(0x80, v & 0xFF);
    xfer16(0x80, v >> 8);
  }
  int bad = 0;
  for (int p = 0; p < N; p++) {
    at(p);
    xfer16(0xC0, 0x00);  // ダミー
    uint16_t lo = xfer16(0xC0, 0x00), hi = xfer16(0xC0, 0x00), got = lo | (hi << 8), want = 0x1000 + p * 37;
    if (got != want) bad++;
    int from = (int)got - 0x1000;
    Serial.printf("Z %5.2f MB: got 0x%04X want 0x%04X%s", p * 0.5, got, want, got == want ? "\n" : "");
    if (got != want) Serial.printf("  <-- overwritten by the write at %.2f MB\n", (from % 37 == 0 && from >= 0) ? from / 37 * 0.5 : -1.0);
  }
  drawToPage(0);
  Serial.printf("Z board %d (E0=0x%02X): %d of %d slots overwritten\n", curBoard, SDRAM_E0, bad, N);
}

// 表示していないページのデータが時間で化けるかを確かめる (#Y<秒>、選んだ基板): 焼き込みの面をページ 34 に書き、
// すぐと「秒」後に、先頭の 40 行 (19,200 画素) を読み返して照合する。読み返しそのものも表示用メモリを乱すので、読むのは 40 行だけ
uint32_t checkRows(const uint16_t *face, int page, int rows) {
  drawToPage(page);
  writeReg16(0x56, 0); writeReg16(0x58, 0); writeReg16(0x5A, 480); writeReg16(0x5C, 480);
  writeReg16(0x5F, 0); writeReg16(0x61, 0);
  windowFull = true;
  xfer16(0x00, 0x04);
  xfer16(0xC0, 0x00);  // ダミー
  uint32_t bad = 0;
  int rot = rotOf[curBoard];
  for (uint32_t i = 0; i < 480u * rows; i++) {
    uint16_t lo = xfer16(0xC0, 0x00), hi = xfer16(0xC0, 0x00);
    if ((uint16_t)(lo | (hi << 8)) != face[rotatedIndex(i % 480, i / 480, rot)]) bad++;
  }
  drawToPage(0);
  return bad;
}

void retentionTest(int seconds) {
  const uint16_t *face = boardFace(curBoard);
  drawToPage(34);
  drawRegion(face, 0, 0, 480, 480);
  drawToPage(0);
  uint32_t b0 = checkRows(face, 34, 40);
  Serial.printf("Y board %d: page 34 right after writing: %lu of 19200 pixels differ\n", curBoard, (unsigned long)b0);
  for (int s = 0; s < seconds; s++) { delay(1000); if (Serial.available()) break; }
  uint32_t b1 = checkRows(face, 34, 40);
  Serial.printf("Y board %d: page 34 after %d s: %lu of 19200 pixels differ\n", curBoard, seconds, (unsigned long)b1);
}

// ページを丸ごと読み返してシリアルに出す (#X<ページ>、選んだ基板)。"X begin" の行のあと 460,800 バイトそのまま、"X end" で終わる。
// 1MHz で約 15 秒。読み返しは表示用メモリを少し乱すことがある (docs/STATUS.md)
void dumpPage(int page) {
  drawToPage(page);
  writeReg16(0x56, 0); writeReg16(0x58, 0); writeReg16(0x5A, 480); writeReg16(0x5C, 480);
  writeReg16(0x5F, 0); writeReg16(0x61, 0);
  windowFull = true;
  xfer16(0x00, 0x04);
  xfer16(0xC0, 0x00);  // ダミー
  Serial.setTxTimeoutMs(2000);  // 普段は送れない分を捨てる設定 (0)。ここでは 1 バイトも落とせないので待つ
  Serial.println("X begin");
  static uint8_t buf[960];
  for (int y = 0; y < 480; y++) {
    for (int i = 0; i < 960; i++) buf[i] = xfer16(0xC0, 0x00);
    Serial.write(buf, 960);
  }
  Serial.flush();
  drawToPage(0);
  Serial.println("\nX end");
  Serial.setTxTimeoutMs(0);
}

// ---- パラパラ漫画 (#R で表示用メモリのページに直接受け、#M で再生) ----
// コマ k は各基板のページ FLIP_BASE + k (#G が使う 0〜3 と、スプライトの続きを避ける)。24 コマで約 11MB、16MB に収まる。
// 送る側 (host/clouds_hourly.py) で基板ごとの面と回転を済ませた、パネルの並びの画素を受ける
static const int FLIP_BASE = 8, FLIP_MAX = 26;  // ページ 8〜33 (33 x 460,800 = 15.2MB)
int flipFrames = 0;

void receivePage(int b, int k) {
  const uint32_t total = 480u * 480u * 2u, chunk = 4096;
  if (b < 0 || b >= NUM_BOARDS || k < 0 || k >= FLIP_MAX) { Serial.println("R error: board or frame out of range"); return; }
  static uint8_t buf[4096];
  while (Serial.available()) Serial.read();
  int keep = curBoard;
  curBoard = b;
  drawToPage(FLIP_BASE + k);
  writeReg16(0x56, 0);
  writeReg16(0x58, 0);
  writeReg16(0x5A, 480);
  writeReg16(0x5C, 480);
  writeReg16(0x5F, 0);
  writeReg16(0x61, 0);
  windowFull = true;
  xfer16(0x00, 0x04);
  Serial.println("R ready");
  SPISettings fast(pixelHz, MSBFIRST, SPI_MODE3);
  uint32_t got = 0, t0 = millis();
  while (got < total) {
    uint32_t want = min(chunk, total - got), n = 0, last = millis();
    while (n < want) {
      int a = Serial.available();
      if (a > 0) { n += Serial.readBytes(buf + n, min((uint32_t)a, want - n)); last = millis(); }
      else if (millis() - last > 3000) { Serial.printf("R error: timeout at %lu\n", (unsigned long)(got + n)); drawToPage(0); curBoard = keep; return; }
    }
    for (uint32_t i = 0; i < n; i += 64) {  // 64 バイトのバーストごとに書き込み FIFO の空きを待つ
      uint32_t w0 = millis();
      while (readStatus() & 0x80) {
        if (millis() - w0 > 100) { Serial.println("R error: FIFO"); drawToPage(0); curBoard = keep; return; }
      }
      SPI.beginTransaction(fast);
      selectLine(SEL_LT);
      SPI.transfer(0x80);
      SPI.writeBytes(buf + i, min((uint32_t)64, n - i));
      selectLine(SEL_NONE);
      SPI.endTransaction();
    }
    got += n;
    Serial.print("k");
  }
  drawToPage(0);
  curBoard = keep;
  if (k + 1 > flipFrames) flipFrames = k + 1;
  Serial.printf("\nR done %d %d in %lu ms\n", b, k, (unsigned long)(millis() - t0));
}

// 全基板でコマ 0..frames-1 を ms ごとに切り替えて繰り返す。シリアルに何か届いたら止めて、ページ 0 に戻す
void playFlip(int ms, int frames) {
  if (frames <= 0 || frames > flipFrames) frames = flipFrames;
  if (frames == 0) { Serial.println("M error: no frames (send them with #R)"); return; }
  while (Serial.available()) Serial.read();
  Serial.printf("M playing %d frames, %d ms each (send anything to stop)\n", frames, ms);
  int keep = curBoard;
  for (int k = 0; !Serial.available(); k = (k + 1) % frames) {
    uint32_t t0 = millis();
    for (int b = 0; b < NUM_BOARDS; b++) { curBoard = b; showPage(FLIP_BASE + k); }
    while (millis() - t0 < (uint32_t)ms && !Serial.available()) delay(1);
  }
  while (Serial.available()) Serial.read();
  for (int b = 0; b < NUM_BOARDS; b++) { curBoard = b; showPage(0); }
  curBoard = keep;
  Serial.println("M stopped");
}

// ---- 表示用メモリの中の複数の画面 (ダブルバッファ用) ----
// LT7680A-R の表示用メモリは 16MB。480x480 の 16 ビット色 1 枚 (460,800 バイト) を「ページ」と呼び、
// ページ 0 と 1 を表と裏、ページ 2 を地球の画像 (消すときのコピー元) に使う
static const uint32_t PAGE_BYTES = 480u * 480u * 2u;
#ifndef PAGE_STRIDE
#define PAGE_STRIDE PAGE_BYTES  // 試験: -DPAGE_STRIDE=0x80000 でページを 512KB おきに置く
#endif
uint32_t pageAddr(int page) { return (uint32_t)PAGE_STRIDE * page; }

// 主画面 (パネルに映す) の開始アドレス。REG[23h] を書いた時点で反映される
void showPage(int page) { writeReg32(0x20, pageAddr(page)); }

// 表示の開始アドレスは、書いた瞬間ではなく次の垂直同期でパネルに効く (と考えると #G のちらつきが説明できた)。
// 切り替えた直後に垂直同期の旗 (REG[0Ch] bit4、REG[0Bh] bit4 で有効) を消しておき、古いページに触る前に旗が立つのを待つ。
// 待たずに古いページで印を消すと、まだ映っているページから印が消えて、ちらつく
void vsyncArm() {
  writeReg(0x0B, readReg(0x0B) | 0x10);
  writeReg(0x0C, 0x10);
}

void vsyncWait() {
  uint32_t t0 = millis();
  while (!(readStatusOrFlag() & 0x10)) {
    if (millis() - t0 > 50) { Serial.printf("TIMEOUT waiting for VSYNC (board %d)\n", curBoard); return; }
  }
}

uint8_t readStatusOrFlag() { return readReg(0x0C); }

// キャンバス (画素の書き込みと図形の描画の行き先) の開始アドレス
void drawToPage(int page) { writeReg32(0x50, pageAddr(page)); }

void waitBte() {
  uint32_t t0 = millis();
  while (readReg(0x90) & 0x10) {
    if (millis() - t0 > 100) { Serial.printf("TIMEOUT waiting for BTE (board %d)\n", curBoard); return; }
  }
}

// LT7680 の中で、ページ sp の (sx, sy) から w x h をページ dp の (dx, dy) へ写す (BTE の Memory Copy、ROP = S0)
void bteCopy(int sp, int sx, int sy, int dp, int dx, int dy, int w, int h) {
  writeReg32(0x93, pageAddr(sp));
  writeReg16(0x97, 480);
  writeReg16(0x99, sx);
  writeReg16(0x9B, sy);
  writeReg32(0xA7, pageAddr(dp));
  writeReg16(0xAB, 480);
  writeReg16(0xAD, dx);
  writeReg16(0xAF, dy);
  writeReg16(0xB1, w);
  writeReg16(0xB3, h);
  writeReg(0x92, 0x25);  // S0、S1、行き先とも 16bpp
  writeReg(0x91, 0xC2);  // ROP = S0、Memory Copy with ROP
  writeReg(0x90, 0x10);  // 開始
  waitBte();
}

// 1 歩目の確かめ (#B): 地球の画像をページ 2 に書き、LT7680 の中でページ 1 へ写して、表示をページ 1 に切り替える。
// そのあと、ページ 1 の左上 1/4 だけを黒く塗ってから、ページ 2 の同じ所を写して戻す
void pageSelfTest() {
  uint32_t t0 = millis();
  drawToPage(2);
  drawRegion(boardFace(curBoard), 0, 0, 480, 480);
  uint32_t t1 = millis();
  bteCopy(2, 0, 0, 1, 0, 0, 480, 480);
  uint32_t t2 = millis();
  showPage(1);
  Serial.printf("cmd B: board %d face to page 2 in %lu ms, copied to page 1 in %lu ms, showing page 1\n", curBoard,
                (unsigned long)(t1 - t0), (unsigned long)(t2 - t1));
  drawToPage(1);
  delay(1500);
  fillRect(0, 0, 239, 239, 0x0000);
  Serial.println("cmd B: page 1 top left black");
  delay(1500);
  uint32_t t3 = micros();
  bteCopy(2, 0, 0, 1, 0, 0, 240, 240);
  Serial.printf("cmd B: top left restored from page 2 in %lu us\n", (unsigned long)(micros() - t3));
  drawToPage(0);
}

// レジスタだけを続けて読み書きする間、SPI を hz で握ったままにする (画素のバーストを挟む所では使わない)
struct RegBurst {
  RegBurst(uint32_t hz) { SPI.beginTransaction(SPISettings(hz, MSBFIRST, SPI_MODE3)); regHeld = true; }
  ~RegBurst() { regHeld = false; SPI.endTransaction(); }
};

// ---- #G: ダブルバッファで飛行機と船を動かす ----
// ページ 0 と 1 を表と裏、ページ 2 を地球の画像にし、ページ 3 から先にスプライト (印とラベルの絵) を並べる。
// 毎コマ、裏のページで「2 コマ前に描いた四角を地球の画像から写して消す」→「新しい場所へスプライトを透明色付きで写す」をして、
// 全部済んでから表示を裏のページに切り替える。途中の状態は画面に出ないので、消す順番を気にしなくてよい
static const uint16_t KEY = 0xF81F;  // 透明色 (マゼンタ)
static const int SHEET_PAGE = 3, BLOCK_W = 80, BLOCK_H = 48, BLOCKS_PER_ROW = 480 / BLOCK_W;

// BTE で、ページ sp の (sx, sy) から w x h をページ dp の (dx, dy) へ写す。key なら透明色の画素は写さない。
// 行き先が画面からはみ出す分は切る
void bteBlit(int sp, int sx, int sy, int dp, int dx, int dy, int w, int h, bool key) {
  if (dx < 0) { sx -= dx; w += dx; dx = 0; }
  if (dy < 0) { sy -= dy; h += dy; dy = 0; }
  if (dx + w > 480) w = 480 - dx;
  if (dy + h > 480) h = 480 - dy;
  if (w <= 0 || h <= 0) return;
  writeReg32C(0x93, pageAddr(sp));
  writeReg16C(0x97, 480);
  writeReg16C(0x99, sx);
  writeReg16C(0x9B, sy);
  writeReg32C(0xA7, pageAddr(dp));
  writeReg16C(0xAB, 480);
  writeReg16C(0xAD, dx);
  writeReg16C(0xAF, dy);
  writeReg16C(0xB1, w);
  writeReg16C(0xB3, h);
  writeRegC(0x92, 0x25);
  writeRegC(0x91, key ? 0xC5 : 0xC2);  // Memory Copy with chroma key / with ROP (S0)
  writeReg(0x90, 0x10);
  waitBte();
}

SpriteGeom spriteGeom(const GMover &m, int q) {
  int s = m.size, W = strlen(m.label) * 5, g = W ? 2 : 0;
  SpriteGeom r;
  if (!(q & 1)) {
    r.w = s + g + W; r.h = max(s, 7);
    r.ox = 0; r.oy = q == 0 ? 0 : 16;
    r.my = (r.h - s) / 2; r.ly = (r.h - 7) / 2;
    if (q == 0) { r.mx = 0; r.lx = s + g; } else { r.mx = W + g; r.lx = 0; }
  } else {
    r.w = max(s, 7); r.h = s + g + W;
    r.ox = q == 1 ? 48 : 64; r.oy = 0;
    r.mx = (r.w - s) / 2; r.lx = (r.w - 7) / 2;
    if (q == 1) { r.my = W + g; r.ly = 0; } else { r.my = 0; r.ly = s + g; }
  }
  return r;
}

// スプライトの (x, y) の色 (透明なら KEY)
uint16_t spritePixel(const GMover &m, int q, const SpriteGeom &g, int x, int y) {
  uint16_t col = m.ship ? 0xFFFF : 0xFFE0;
  int s = m.size, c = s / 2, dx = x - g.mx, dy = y - g.my;
  if (dx >= 0 && dy >= 0 && dx < s && dy < s && (m.ship || abs(dx - c) <= 1 || abs(dy - c) <= 1)) return col;
  int W = strlen(m.label) * 5, u = x - g.lx, v = y - g.ly, tx, ty;
  if (!W || u < 0 || v < 0 || u >= ((q & 1) ? 7 : W) || v >= ((q & 1) ? W : 7)) return KEY;
  switch (q) {
    case 1: tx = W - 1 - v; ty = u; break;
    case 2: tx = W - 1 - u; ty = 6 - v; break;
    case 3: tx = v; ty = 6 - u; break;
    default: tx = u; ty = v; break;
  }
  char ch = m.label[tx / 5];
  if (ch < 32 || ch > 95) return KEY;
  return (FONT5X7[ch - 32][ty] >> (4 - tx % 5)) & 1 ? col : KEY;
}

// 選んだ基板のキャンバス (今のページ) の (x0, y0) から w x h に、px(x, y) の色を書く。y は 480 を超えてよい (ページをまたぐ)
template <typename F> void streamPixels(int x0, int y0, int w, int h, F px) {
  writeReg16(0x56, x0);
  writeReg16(0x58, y0);
  writeReg16(0x5A, w);
  writeReg16(0x5C, h);
  writeReg16(0x5F, x0);
  writeReg16(0x61, y0);
  windowFull = false;
  xfer16(0x00, 0x04);
  SPISettings fast(pixelHz, MSBFIRST, SPI_MODE3);
  uint8_t buf[64];
  int n = 0;
  uint32_t count = (uint32_t)w * h;
  for (uint32_t i = 0; i < count; i++) {
    uint16_t c = px(i % w, i / w);
    buf[n++] = c & 0xFF;
    buf[n++] = c >> 8;
    if (n == sizeof(buf) || i == count - 1) {
      uint32_t w0 = millis();
      while (readStatus() & 0x80) {
        if (millis() - w0 > 100) { Serial.printf("TIMEOUT waiting for write FIFO (board %d)\n", curBoard); return; }
      }
      SPI.beginTransaction(fast);
      selectLine(SEL_LT);
      SPI.transfer(0x80);
      SPI.writeBytes(buf, n);
      selectLine(SEL_NONE);
      SPI.endTransaction();
      n = 0;
    }
  }
}

void demoDouble(int seconds, bool labels, int planesPerBoard, bool vsync, uint32_t burstHz) {
  const int PLANES = planesPerBoard * NUM_BOARDS, SHIPS = 4 * NUM_BOARDS, N = PLANES + SHIPS;
  GMover *m = (GMover *)calloc(N, sizeof(GMover));
  if (!m) { Serial.println("cmd G: out of memory"); return; }
  randomSeed(esp_random());
  for (int k = 0; k < N; k++) {
    GMover &o = m[k];
    o.ship = k >= PLANES;
    o.size = o.ship ? 5 : 11;
    o.speed = o.ship ? 0.0005f : random(25, 60) / 10000.0f;
    if (!labels) o.label[0] = 0;
    else if (o.ship) snprintf(o.label, sizeof(o.label), "MARU-%d", k - PLANES + 1);
    else snprintf(o.label, sizeof(o.label), "%s%03d", (k % 2) ? "JL" : "NH", (int)random(100, 999));
    for (int t = 0; t < 500; t++) {
      randomPoint(o.p);
      int b, px, py, f, fx, fy;
      locate(o.p, o.size, &b, &px, &py, &f, &fx, &fy);
      if (b >= 0 && (!o.ship || isSeaPixel(f, fx, fy))) break;
    }
    float tmp[3];
    memcpy(tmp, o.p, sizeof(tmp));
    Mover h;  // randomHeading は Mover を受けるので、向きだけ借りる
    memcpy(h.p, o.p, sizeof(h.p));
    randomHeading(h);
    memcpy(o.d, h.d, sizeof(o.d));
    for (int pg = 0; pg < 2; pg++) o.rb[pg] = -1;
  }
  int keep = curBoard;
  uint32_t s0 = millis();
  regCacheClear();
  for (int b = 0; b < NUM_BOARDS; b++) {  // 地球の画像をページ 2 に、表と裏に写す。スプライトを描く
    curBoard = b;
    drawToPage(2);
    drawRegion(boardFace(b), 0, 0, 480, 480);
    bteCopy(2, 0, 0, 0, 0, 0, 480, 480);
    bteCopy(2, 0, 0, 1, 0, 0, 480, 480);
    regCacheClear();
    drawToPage(SHEET_PAGE);
    for (int k = 0; k < N; k++) {
      int bx = (k % BLOCKS_PER_ROW) * BLOCK_W, by = (k / BLOCKS_PER_ROW) * BLOCK_H;
      for (int q = 0; q < 4; q++) {
        SpriteGeom g = spriteGeom(m[k], q);
        streamPixels(bx + g.ox, by + g.oy, g.w, g.h, [&](int x, int y) { return spritePixel(m[k], q, g, x, y); });
        if (!labels) break;  // ラベルが無ければ向きは要らない
      }
    }
    showPage(0);
    drawToPage(0);
  }
  for (int b = 0; b < NUM_BOARDS; b++) { curBoard = b; writeRegC(0xD5, 0xF8); writeRegC(0xD6, 0x00); writeRegC(0xD7, 0xF8); }  // 透明色
  Serial.printf("cmd G: setup %lu ms (%d movers)\n", (unsigned long)(millis() - s0), N);

  int front = 0;
  uint32_t t0 = millis(), frames = 0, busy = 0, worst = 0, shown = 0, nearEdge = 0;
  uint32_t checks = 0, badRegs[NUM_BOARDS] = {}, firstBad[NUM_BOARDS] = {};
  int printed = 0;
  while (millis() - t0 < (uint32_t)seconds * 1000) {
    uint32_t f0 = micros();
    int back = 1 - front;
    RegBurst burst(burstHz);  // このコマはレジスタと BTE だけなので、SPI を握ったまま速く回す
    for (int i = 0; i < N; i++) {  // 進める
      GMover &o = m[i];
      float c = cosf(o.speed), s = sinf(o.speed), np[3], nd[3];
      for (int j = 0; j < 3; j++) { np[j] = o.p[j] * c + o.d[j] * s; nd[j] = o.d[j] * c - o.p[j] * s; }
      if (o.ship) {
        float x, y;
        int f = qscProject(qsc, np, &x, &y);
        if (!isSeaPixel(f, (int)x, (int)y)) {
          Mover h;
          memcpy(h.p, o.p, sizeof(h.p));
          randomHeading(h);
          memcpy(o.d, h.d, sizeof(o.d));
          continue;
        }
      }
      memcpy(o.p, np, sizeof(np));
      memcpy(o.d, nd, sizeof(nd));
    }
    for (int i = 0; i < N; i++) {  // 描く基板と場所、ラベルの向きを先に決める
      GMover &o = m[i];
      locate(o.p, o.size, &o.nb, &o.cx, &o.cy, &o.f, &o.fx, &o.fy);
      o.q = (o.nb >= 0 && labels) ? southOnPanel(o.p, o.nb) : 0;
      o.eb = o.rb[back];
      o.ex = o.rx[back];
      o.ey = o.ry[back];
      o.ew = o.rw[back];
      o.eh = o.rh[back];
      o.rb[back] = -1;
      if (o.nb >= 0) {
        shown++;
        if (min(min(o.cx, o.cy), min(479 - o.cx, 479 - o.cy)) < 8) nearEdge++;
      }
    }
    // 基板ごとに「前の切り替えが効くのを待つ → 2 コマ前の四角を消す → 描く → 切り替える」。
    // 基板 0 を待つ間に基板 1、2 の切り替えも効いていくので、待ち時間が重ならない
    for (int b = 0; b < NUM_BOARDS; b++) {
      curBoard = b;
      if (vsync && frames > 0) vsyncWait();
      for (int i = 0; i < N; i++) {
        GMover &o = m[i];
        if (o.eb != b) continue;  // 基板を移った飛行機は、前の基板の番で消す
        bteBlit(2, o.ex, o.ey, back, o.ex, o.ey, o.ew, o.eh, false);
      }
      for (int i = 0; i < N; i++) {
        GMover &o = m[i];
        if (o.nb != b) continue;
        SpriteGeom g = spriteGeom(o, o.q);
        int sx = (i % BLOCKS_PER_ROW) * BLOCK_W + g.ox, sy = (i / BLOCKS_PER_ROW) * BLOCK_H + g.oy;
        int dx = o.cx - o.size / 2 - g.mx, dy = o.cy - o.size / 2 - g.my;
        bteBlit(SHEET_PAGE, sx, sy, back, dx, dy, g.w, g.h, true);
        o.rx[back] = max(dx, 0);
        o.ry[back] = max(dy, 0);
        o.rw[back] = min(dx + g.w, 480) - o.rx[back];
        o.rh[back] = min(dy + g.h, 480) - o.ry[back];
        o.rb[back] = (o.rw[back] > 0 && o.rh[back] > 0) ? b : -1;
      }
      showPage(back);
      if (vsync) vsyncArm();
    }
    front = back;
    frames++;
    if (frames % 30 == 0) {  // 1 秒ごとに、各基板のレジスタを読み返す (reg_verify.h)
      checks++;
      for (int b = 0; b < NUM_BOARDS; b++) {
        curBoard = b;
        RegExpect e[REG_VERIFY_MAX];
        int n = cacheExpect(e, gExpect(e, pageAddr(front)), regCache[b], 0x93, 0xB4);
        int bad = verifyRegs(e, n, readReg, [&](uint8_t r, uint8_t want, uint8_t got, uint8_t again) {
          if (printed++ < 40) Serial.printf("verify: %lu ms board %d REG[%02Xh] %02X, again %02X, want %02X\n", (unsigned long)(millis() - t0), b, r, got, again, want);
        });
        if (bad && !badRegs[b]) firstBad[b] = millis() - t0;
        badRegs[b] += bad;
      }
    }
    uint32_t spent = micros() - f0;
    busy += spent;
    worst = max(worst, spent);
    if (spent < 33000) delay((33000 - spent) / 1000);
  }
  for (int b = 0; b < NUM_BOARDS; b++) {  // 片付け: 地球だけのページ 2 を表示に写して、ページ 0 に戻す
    curBoard = b;
    bteCopy(2, 0, 0, 0, 0, 0, 480, 480);
    showPage(0);
    drawToPage(0);
  }
  regCacheClear();
  curBoard = keep;
  free(m);
  Serial.printf("cmd G: verify %lu checks", (unsigned long)checks);
  for (int b = 0; b < NUM_BOARDS; b++) Serial.printf(", board %d %lu bad (first %lu ms)", b, (unsigned long)badRegs[b], (unsigned long)firstBad[b]);
  Serial.println();
  Serial.printf("cmd G: drawn %lu times, %.1f%% within 8 px of the panel edge\n", (unsigned long)shown, 100.0 * nearEdge / (shown ? shown : 1));
  Serial.printf("cmd G: %s, %d movers%s, %lu frames in %d s, work %.1f ms/frame (worst %.1f), %.0f fps if not held to 30\n", vsync ? "vsync" : "no vsync", N,
                labels ? " with labels" : "", (unsigned long)frames, seconds, busy / 1000.0 / frames, worst / 1000.0, frames * 1e6 / busy);
}

// 架空の飛行機と船を動かす (#D<秒>)。位置は経度・緯度 (単位ベクトル) で持ち、大円に沿って進める。
// 毎コマ QSC 投影で面と画素に直し、その面を映している基板に、基板の回転を付けて描くので、面の境目をそのまままたぐ。
// 飛行機は黄色い十字、船は白い点で、船は進む先が陸 (面の画像で海の色でない画素) なら向きを変える。
// 1 機ごとに、前の場所と新しい場所を囲む四角を、面の画像に印を重ねて 1 回で書く (消してから描くとちらつく)

bool isSeaPixel(int face, int x, int y) {
  uint16_t c = EARTH_QSC480X6[face][constrain(y, 0, 479) * 480 + constrain(x, 0, 479)];
  int r = c >> 11, g = (c >> 5) & 63, b = c & 31;
  return r < 6 && g < 12 && b >= 6;  // Blue Marble の海は暗い紺
}

// 印かラベルが (x, y) を覆っていればその色、覆っていなければ -1。
// 船は白い四角、飛行機は黄色い十字 (胴体と翼、太さ 3)、ラベルは 5x7 の文字で印と同じ色
int moverColorAt(const Mover &m, int x, int y) {
  if (m.board < 0 || x < m.bx || y < m.by || x >= m.bx + m.bw || y >= m.by + m.bh) return -1;
  uint16_t col = m.ship ? 0xFFFF : 0xFFE0;
  int dx = x - m.mx, dy = y - m.my, s = m.size, c = s / 2;
  if (dx >= 0 && dy >= 0 && dx < s && dy < s) {
    if (m.ship || abs(dx - c) <= 1 || abs(dy - c) <= 1) return col;
  }
  int W = strlen(m.label) * 5, u = x - m.lx, v = y - m.ly, tx, ty;  // (u, v): ラベルの四角の中、(tx, ty): 回す前の文字列の中
  bool side = m.lq & 1;
  if (u < 0 || v < 0 || u >= (side ? 7 : W) || v >= (side ? W : 7)) return -1;
  switch (m.lq) {
    case 1: tx = W - 1 - v; ty = u; break;      // 文字の下が右 (90 度左に回す)
    case 2: tx = W - 1 - u; ty = 6 - v; break;  // 文字の下が上
    case 3: tx = v; ty = 6 - u; break;          // 文字の下が左 (90 度右に回す)
    default: tx = u; ty = v; break;
  }
  char ch = m.label[tx / 5];
  if (ch < 32 || ch > 95) return -1;
  return (FONT5X7[ch - 32][ty] >> (4 - tx % 5)) & 1 ? col : -1;
}

// 点 p の南の向きを、基板 b のパネルの上の 4 方向 (lq と同じ番号) で返す。p の少し南の点との差を投影して、回転を付けて決める
int southOnPanel(const float *p, int b) {
  float nv[3] = {-p[2] * p[0], -p[2] * p[1], 1 - p[2] * p[2]}, len = sqrtf(qscDot(nv, nv));  // p での北の向き
  if (len < 1e-4f) return 0;  // 極そのもの
  float q[3], x0, y0, x1, y1;
  for (int i = 0; i < 3; i++) q[i] = p[i] - 0.01f * nv[i] / len;
  int f0 = qscProject(qsc, p, &x0, &y0), f1 = qscProject(qsc, q, &x1, &y1);
  float dx = x1 - x0, dy = y1 - y0;
  if (f1 != f0) {  // 南の点が隣の面に出た: 北へずらした点との差を逆向きに使う
    for (int i = 0; i < 3; i++) q[i] = p[i] + 0.01f * nv[i] / len;
    qscProject(qsc, q, &x1, &y1);
    dx = x0 - x1;
    dy = y0 - y1;
  }
  float X, Y;  // 画像の向きをパネルの向きへ (panelOf と同じ回し方)
  switch (rotOf[b] & 3) {
    case 1: X = -dy; Y = dx; break;
    case 2: X = -dx; Y = -dy; break;
    case 3: X = dy; Y = -dx; break;
    default: X = dx; Y = dy; break;
  }
  if (fabsf(Y) >= fabsf(X)) return Y > 0 ? 0 : 2;
  return X > 0 ? 1 : 3;
}

// 印の中心 (cx, cy) から、印、ラベル、それらを囲む四角の位置を決める。ラベルは文字の向き lq で、
// 読む向きの先 (lq 0: 右、1: 上、2: 左、3: 下) に置き、パネルに収まらなければ反対側に置く
void placeMover(Mover &m, int cx, int cy, int lq) {
  int s = m.size, W = strlen(m.label) * 5;
  m.mx = constrain(cx - s / 2, 0, 480 - s);
  m.my = constrain(cy - s / 2, 0, 480 - s);
  m.lq = lq;
  if (W == 0) { m.bx = m.mx; m.by = m.my; m.bw = s; m.bh = s; m.lx = m.ly = -100; return; }
  int lw = (lq & 1) ? 7 : W, lh = (lq & 1) ? W : 7;
  int ccx = m.mx + s / 2, ccy = m.my + s / 2;
  // 読む向きの先と、その反対
  int ax[4] = {m.mx + s + 2, ccx - lw / 2, m.mx - 2 - lw, ccx - lw / 2};
  int ay[4] = {ccy - lh / 2, m.my - 2 - lh, ccy - lh / 2, m.my + s + 2};
  int dir = lq == 0 ? 0 : lq == 1 ? 1 : lq == 2 ? 2 : 3;
  int lx = ax[dir], ly = ay[dir];
  if (lx < 0 || ly < 0 || lx + lw > 480 || ly + lh > 480) { lx = ax[(dir + 2) % 4]; ly = ay[(dir + 2) % 4]; }
  m.lx = constrain(lx, 0, 480 - lw);
  m.ly = constrain(ly, 0, 480 - lh);
  m.bx = min(m.mx, m.lx);
  m.by = min(m.my, m.ly);
  m.bw = max(m.mx + s, m.lx + lw) - m.bx;
  m.bh = max(m.my + s, m.ly + lh) - m.by;
}

// 進む向きをランダムに選び直す (p に直交する単位ベクトル)
void randomHeading(Mover &o) {
  float a[3] = {random(-1000, 1000) / 1000.0f, random(-1000, 1000) / 1000.0f, random(-1000, 1000) / 1000.0f};
  float k = qscDot(a, o.p), len = 0;
  for (int i = 0; i < 3; i++) { o.d[i] = a[i] - k * o.p[i]; len += o.d[i] * o.d[i]; }
  len = sqrtf(len);
  if (len < 1e-3f) { randomHeading(o); return; }
  for (int i = 0; i < 3; i++) o.d[i] /= len;
}

void randomPoint(float *v) {
  float z = random(-1000, 1000) / 1000.0f, a = random(0, 6283) / 1000.0f, r = sqrtf(1 - z * z);
  qscSet(v, r * cosf(a), r * sinf(a), z);
}

// 点 v を描く基板と、その基板のパネルでの位置を求める。どの基板の面にも載っていなければ board = -1
void locate(const float *v, int size, int *board, int *px, int *py, int *face, int *fx, int *fy) {
  float x, y;
  *face = qscProject(qsc, v, &x, &y);
  *fx = constrain((int)x, 0, 479);
  *fy = constrain((int)y, 0, 479);
  *board = -1;
  for (int b = 0; b < NUM_BOARDS; b++)
    if (faceOf[b] == *face) { *board = b; break; }
  if (*board < 0) return;
  uint32_t X, Y;
  panelOf(*fx, *fy, rotOf[*board], &X, &Y);
  *px = X;  // 印の中心
  *py = Y;
}

bool onShownFace(const float *v) {
  int b, px, py, f, fx, fy;
  locate(v, 1, &b, &px, &py, &f, &fx, &fy);
  return b >= 0;
}

void demoMovers(int seconds, bool labels, int planesPerBoard) {
  const int PLANES = planesPerBoard * NUM_BOARDS, SHIPS = 4 * NUM_BOARDS, N = PLANES + SHIPS;
  Mover *m = (Mover *)calloc(N, sizeof(Mover));  // 数百機はスタックに載らない
  if (!m) { Serial.println("cmd D: out of memory"); return; }
  randomSeed(esp_random());
  for (int k = 0; k < N; k++) {
    Mover &o = m[k];
    o.ship = k >= PLANES;
    o.size = o.ship ? 5 : 11;
    o.speed = (o.ship ? 0.0005f : random(25, 60) / 10000.0f);  // ラジアン/コマ (飛行機は 0.14〜0.34 度)
    o.board = -1;
    if (!labels) o.label[0] = 0;
    else if (o.ship) snprintf(o.label, sizeof(o.label), "MARU-%d", k - PLANES + 1);
    else snprintf(o.label, sizeof(o.label), "%s%03d", (k % 2) ? "JL" : "NH", (int)random(100, 999));
    for (int t = 0; t < 500; t++) {  // 映っている面の上 (船は海の上) から始める
      randomPoint(o.p);
      int b, px, py, f, fx, fy;
      locate(o.p, o.size, &b, &px, &py, &f, &fx, &fy);
      if (b >= 0 && (!o.ship || isSeaPixel(f, fx, fy))) break;
    }
    randomHeading(o);
  }
  int keep = curBoard;
  uint32_t t0 = millis(), frames = 0, busy = 0, worst = 0;
  while (millis() - t0 < (uint32_t)seconds * 1000) {
    uint32_t f0 = micros();
    for (int i = 0; i < N; i++) {
      Mover &o = m[i];
      float c = cosf(o.speed), s = sinf(o.speed), np[3], nd[3];
      for (int j = 0; j < 3; j++) {
        np[j] = o.p[j] * c + o.d[j] * s;
        nd[j] = o.d[j] * c - o.p[j] * s;
      }
      int nb, npx, npy, f, fx, fy;
      locate(np, o.size, &nb, &npx, &npy, &f, &fx, &fy);
      if (o.ship && !isSeaPixel(f, fx, fy)) {  // 陸に当たったら向きを変えて、このコマは止まる
        randomHeading(o);
        continue;
      }
      memcpy(o.p, np, sizeof(np));
      memcpy(o.d, nd, sizeof(nd));
      Mover old = o;
      if (nb >= 0) placeMover(o, npx, npy, o.label[0] ? southOnPanel(np, nb) : 0);
      o.board = nb;
      if (nb == old.board && (nb < 0 || (o.bx == old.bx && o.by == old.by && o.bw == old.bw))) continue;  // 画素が変わらなければ書かない
      int ux = min(o.bx, old.bx), uy = min(o.by, old.by);
      int uw = max(o.bx + o.bw, old.bx + old.bw) - ux, uh = max(o.by + o.bh, old.by + old.bh) - uy;
      bool together = old.board >= 0 && nb == old.board && uw * uh <= 2 * (o.bw * o.bh + old.bw * old.bh);
      if (old.board >= 0 && !together) {  // 別の基板へ移った (面の境目をまたいだ) か大きく飛んだ: 前の場所を消す
        curBoard = old.board;
        drawRegionOver(boardFace(old.board), old.bx, old.by, old.bw, old.bh, m, N);
      }
      if (nb < 0) continue;  // 映っていない面にいる
      curBoard = nb;
      if (together) drawRegionOver(boardFace(nb), ux, uy, uw, uh, m, N);
      else drawRegionOver(boardFace(nb), o.bx, o.by, o.bw, o.bh, m, N);
    }
    frames++;
    uint32_t spent = micros() - f0;
    busy += spent;
    worst = max(worst, spent);
    if (spent < 33000) delay((33000 - spent) / 1000);  // 30 コマ/秒に揃える
  }
  for (int i = 0; i < N; i++) {  // 片付け
    if (m[i].board < 0) continue;
    int b = m[i].board;
    m[i].board = -1;
    curBoard = b;
    drawRegionOver(boardFace(b), m[i].bx, m[i].by, m[i].bw, m[i].bh, m, N);
  }
  curBoard = keep;
  free(m);
  Serial.printf("cmd D: %d movers%s, %lu frames in %d s, work %.1f ms/frame (worst %.1f), %.0f fps if not held to 30\n", N, labels ? " with labels" : "",
                (unsigned long)frames, seconds, busy / 1000.0 / frames, worst / 1000.0, frames * 1e6 / busy);
}

// 印を動かす速さを測る: 1 コマごとに、前の印の場所を face で描き直し、新しい場所に s x s の赤い四角を塗る。
// 面の真ん中の行を左から右へ 2 画素ずつ、frames コマ動かし、1 コマの平均と fps を報告する
void benchMarker(int frames, int s) {
  const uint16_t *face = boardFace(curBoard);
  int px = -1, y = 240 - s / 2;
  uint32_t tRestore = 0, tMark = 0, t0 = micros();
  for (int i = 0; i < frames; i++) {
    int x = (i * 2) % (480 - s);
    uint32_t a = micros();
    if (px >= 0) drawRegion(face, px, y, s, s);
    uint32_t b = micros();
    fillRect(x, y, x + s - 1, y + s - 1, 0xF800);
    tRestore += b - a;
    tMark += micros() - b;
    px = x;
  }
  uint32_t dt = micros() - t0;
  drawRegion(face, px, y, s, s);
  Serial.printf("cmd T: board %d, %d frames of %dx%d in %lu ms: %.2f ms/frame (restore %.2f, mark %.2f), %.1f fps\n", curBoard, frames, s, s,
                (unsigned long)(dt / 1000), dt / 1000.0 / frames, tRestore / 1000.0 / frames, tMark / 1000.0 / frames, frames * 1e6 / dt);
}

// 選んだ基板の表示用メモリを全画素読み返し、face と照合する (1MHz、約 20 秒)。
// ポートを選び直した直後の 1 回は捨てる (データシート REG[04h] Note1)
uint32_t verifyFace(const uint16_t *face) {
  writeReg16(0x56, 0);
  writeReg16(0x58, 0);
  writeReg16(0x5A, 480);
  writeReg16(0x5C, 480);
  writeReg16(0x5F, 0);
  writeReg16(0x61, 0);
  xfer16(0x00, 0x04);
  xfer16(0xC0, 0x00);  // ダミー
  uint32_t bad = 0, t0 = millis();
  for (uint32_t i = 0; i < 480u * 480u; i++) {
    uint16_t lo = xfer16(0xC0, 0x00), hi = xfer16(0xC0, 0x00);
    uint16_t got = lo | (hi << 8), want = face[rotatedIndex(i % 480, i / 480, rotOf[curBoard])];  // drawRegion と同じく回転込み
    if (got != want && bad++ < 5) {
      Serial.printf("verify NG at (%lu,%lu): got 0x%04X want 0x%04X\n", (unsigned long)(i % 480),
                    (unsigned long)(i / 480), got, want);
    }
  }
  Serial.printf("board %d: verify %lu bad pixels of %u in %lu ms\n", curBoard, (unsigned long)bad, 480u * 480u,
                (unsigned long)(millis() - t0));
  return bad;
}

// ---- microSD (XIAO ESP32-S3 Sense の拡張ボード) ----
// カードは LT7680 と同じ SPI (D8 SCK, D9 MISO, D10 MOSI) で、CS だけ GPIO21 (拡張ボードの R12 経由。XIAO の USER_LED と同じピン)。
// SD ライブラリも LT7680 の読み書きも SPI のトランザクションを取るので、交互に使える (はず。#C で確かめる)
#define SD_CS 21
bool cardMounted = false;

bool mountCard(uint32_t hz) {
  if (cardMounted) return true;
  cardMounted = SD.begin(SD_CS, SPI, hz, "/sd", 5);
  if (!cardMounted) Serial.println("card: mount failed");
  return cardMounted;
}

// #C[<MHz>]: 載せて、種類と大きさ、根の一覧を出し、面 1 枚ぶん (480x480x2 バイト) を書いて読み返し、速さを測る
void cardTest(long mhz) {
  if (mhz <= 0) mhz = 10;
  if (cardMounted) { SD.end(); cardMounted = false; }
  if (!mountCard(mhz * 1000000)) return;
  static const char *types[] = {"none", "MMC", "SD", "SDHC", "unknown"};
  uint8_t t = SD.cardType();
  Serial.printf("card: %s, %llu MB, used %llu / %llu MB, SPI %ld MHz\n", types[t < 4 ? t : 4], SD.cardSize() >> 20,
                SD.usedBytes() >> 20, SD.totalBytes() >> 20, mhz);
  File root = SD.open("/");
  int n = 0;
  for (File f = root.openNextFile(); f && n < 20; f = root.openNextFile(), n++)
    Serial.printf("card: /%s%s %u\n", f.name(), f.isDirectory() ? "/" : "", (unsigned)f.size());
  root.close();
  const size_t N = 480 * 480 * 2, CH = 4096;
  static uint8_t buf[4096];
  File f = SD.open("/cubic_test.bin", FILE_WRITE);
  if (!f) { Serial.println("card: open for write failed"); return; }
  uint32_t t0 = millis();
  for (size_t i = 0; i < N; i += CH) {
    size_t n = N - i < CH ? N - i : CH;
    for (size_t j = 0; j < n; j++) buf[j] = (uint8_t)((i + j) * 7 + ((i + j) >> 9));
    f.write(buf, n);
  }
  f.close();
  uint32_t t1 = millis();
  f = SD.open("/cubic_test.bin");
  size_t bad = 0, got = 0;
  for (size_t i = 0; i < N; i += CH) {
    size_t r = f.read(buf, N - i < CH ? N - i : CH);
    got += r;
    for (size_t j = 0; j < r; j++) bad += buf[j] != (uint8_t)((i + j) * 7 + ((i + j) >> 9));
  }
  f.close();
  uint32_t t2 = millis();
  Serial.printf("card: wrote %u bytes in %lu ms, read %u in %lu ms, %u bad bytes%s\n", (unsigned)N, (unsigned long)(t1 - t0),
                (unsigned)got, (unsigned long)(t2 - t1), (unsigned)bad, got == N ? "" : " (short read)");
  SD.remove("/cubic_test.bin");
}

// ---- シーン (microSD の /scenes/<k>/face<f>.bin) ----
// シーン k は 6 面の画像 (face<f>.bin、480x480 RGB565 リトルエンディアン、#U や host/clouds.py の face<f>.bin と同じ並び、回転前)。
// #s<k> で、各基板の面 (faceOf) をシーン k から読んで、回転 (rotOf) を付けて描く。読むのは基板の数だけ
#define SD_HZ 20000000
#define FACE_BYTES (480u * 480u * 2u)
// 読んだ面は #U と同じ faceOverride (PSRAM) に置くので、そのあとの #E、#G (飛行機と船) もシーンの画像を背景に使う。#u で焼き込みに戻る

void scenePath(char *out, size_t n, int k, int f) { snprintf(out, n, "/scenes/%d/face%d.bin", k, f); }

bool loadSceneFace(int k, int f) {
  if (!mountCard(SD_HZ)) return false;
  char path[40];
  scenePath(path, sizeof path, k, f);
  File fl = SD.open(path);
  if (!fl || fl.size() != FACE_BYTES) { Serial.printf("scene: %s missing\n", path); if (fl) fl.close(); return false; }
  if (!faceOverride[f]) faceOverride[f] = (uint16_t *)ps_malloc(FACE_BYTES);
  if (!faceOverride[f]) { Serial.println("scene: no PSRAM"); fl.close(); return false; }
  size_t got = fl.read((uint8_t *)faceOverride[f], FACE_BYTES);
  fl.close();
  return got == FACE_BYTES;
}

void showScene(int k) {
  uint32_t t0 = millis();
  int keep = curBoard, shown = 0;
  for (int b = 0; b < NUM_BOARDS; b++) {
    if (!loadSceneFace(k, faceOf[b])) continue;
    curBoard = b;
    drawToPage(0);
    showPage(0);
    if (drawRegion(boardFace(b), 0, 0, 480, 480)) shown++;
  }
  curBoard = keep;
  Serial.printf("scene %d: %d of %d boards in %lu ms\n", k, shown, NUM_BOARDS, (unsigned long)(millis() - t0));
}

File openSceneForWrite(int k, int f) {
  char path[40];
  snprintf(path, sizeof path, "/scenes/%d", k);
  if (!SD.exists("/scenes")) SD.mkdir("/scenes");
  if (!SD.exists(path)) SD.mkdir(path);
  scenePath(path, sizeof path, k, f);
  return SD.open(path, FILE_WRITE);
}

// #e<k>: 焼き込みの地球の 6 面を、シーン k として書き出す
void exportEarth(int k) {
  if (!mountCard(SD_HZ)) return;
  uint32_t t0 = millis();
  for (int f = 0; f < NUM_FACES; f++) {
    File fl = openSceneForWrite(k, f);
    if (!fl) { Serial.printf("e error: cannot write scene %d face %d\n", k, f); return; }
    fl.write((const uint8_t *)EARTH_QSC480X6[f], FACE_BYTES);
    fl.close();
  }
  Serial.printf("e done: earth as scene %d in %lu ms\n", k, (unsigned long)(millis() - t0));
}

// #w<k>,<f>: 面の画像を #U と同じやり方 (4096 バイトずつ、受けるたびに "k") でシリアルから受け、シーン k の面 f として書く。
// 送り手は host/send_scene.py。本体のバイト列はシリアルからだけ受ける
void receiveSceneFace(int k, int f) {
  const uint32_t chunk = 4096;
  static uint8_t buf[4096];
  if (k < 0 || f < 0 || f >= NUM_FACES) { Serial.println("w error: scene >= 0, face 0-5"); return; }
  if (!mountCard(SD_HZ)) return;
  File fl = openSceneForWrite(k, f);
  if (!fl) { Serial.println("w error: cannot open"); return; }
  while (Serial.available()) Serial.read();
  Serial.println("w ready");
  uint32_t got = 0, t0 = millis();
  while (got < FACE_BYTES) {
    uint32_t want = min(chunk, FACE_BYTES - got), n = 0, last = millis();
    while (n < want) {
      int a = Serial.available();
      if (a > 0) { n += Serial.readBytes(buf + n, min((uint32_t)a, want - n)); last = millis(); }
      else if (millis() - last > 3000) { Serial.printf("w error: timeout at %lu\n", (unsigned long)(got + n)); fl.close(); return; }
    }
    fl.write(buf, n);
    got += n;
    Serial.print("k");
  }
  fl.close();
  Serial.printf("\nw done %d %d in %lu ms\n", k, f, (unsigned long)(millis() - t0));
}

// ---- 起動の流れ ----
// 「流れ」= LT7680 のリセット → PLL/SDRAM → 表示オン → 塗り → パネルの SWRESET + 初期化列 ×2。
// LCM_RESET は全基板で共有なので、リセットは 1 回で全基板に掛かる。その後は基板ごとに設定する
void flowAll(uint16_t color) {
  digitalWrite(PIN_RESET, LOW);
  delay(LT_RESET_HOLD_MS);
  digitalWrite(PIN_RESET, HIGH);
  delay(200);
  for (int b = 0; b < NUM_BOARDS; b++) {
    curBoard = b;
    bool ok = initLt7680NoReset();
    writeReg(0x12, readReg(0x12) | 0x40);  // 表示オン
    setupMemory();
    fillRect(0, 0, 479, 479, color);
    resetAndInitPanel();
    delay(200);
    resetAndInitPanel();
    Serial.printf("board %d: lt7680 %s, panel SWRESET + init x2\n", b, ok ? "OK" : "FAILED");
  }
}

#ifndef BOOT_FLOWS
#define BOOT_FLOWS 2  // BOOT_LEGACY_FLOWS のときだけ使う
#endif

void setup() {
  pinMode(PIN_RESET, OUTPUT_OPEN_DRAIN);
  gpio_pullup_en((gpio_num_t)PIN_RESET);
  digitalWrite(PIN_RESET, HIGH);
  qscInit(qsc, 139.767f, 480);  // earth_qsc480x6.h の面 0 の中心経度
  selectSetup();
  pinMode(PIN_PANEL_SCK, OUTPUT);
  digitalWrite(PIN_PANEL_SCK, LOW);
  pinMode(PIN_PANEL_SDA, OUTPUT);
  digitalWrite(PIN_PANEL_SDA, LOW);
  pinMode(PIN_BL, OUTPUT);
  digitalWrite(PIN_BL, LOW);
  Serial.setRxBufferSize(8192);  // #U で 4096 バイトずつ受ける
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  Serial.setTimeout(200);
#ifndef BOOT_LEGACY_FLOWS
  // メーカー推奨どおりの起動: パネルの RST は基板上の RC (10k/1uF) で、電源投入から 20〜30ms で解除される。
  // それを待ってから、メーカーのデモ (CTP_test.ino) と同じ順で LT7680 の初期化 → ST7701S の初期化 1 回 → 表示オン。
  // LCD_CS がつながっていれば、待ち時間の追加・流れの繰り返し・SWRESET は要らない (USB-C 抜き差しで全回映る)
  while (millis() < 30) delay(1);
  uint32_t t0 = millis();
  loadFaces();
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
  setSpiDrive(SPI_DRIVE);
  digitalWrite(PIN_RESET, LOW);  // LCM_RESET は全基板で共通
  delay(LT_RESET_HOLD_MS);
  digitalWrite(PIN_RESET, HIGH);
  delay(100);
  bool ok[NUM_BOARDS];
  for (int b = 0; b < NUM_BOARDS; b++) {
    curBoard = b;
    ok[b] = initLt7680NoReset();
    if (!ok[b]) continue;  // つないでいない基板は飛ばす (残りの基板とバックライトを止めない)
    initPanel();
    writeReg(0x12, readReg(0x12) | 0x40);  // 表示オン
    setupMemory();
    drawFace(boardFace(curBoard));
  }
  curBoard = 0;
  digitalWrite(PIN_BL, HIGH);
  uint32_t t1 = millis();
  while (millis() < 3000) delay(10);  // シリアルの読み手が付いてから報告する
  Serial.printf("reset reason: %d, boards: %d, select: %s, pixel SPI %lu Hz, drive %d\n", (int)esp_reset_reason(), NUM_BOARDS,
#ifdef BOARD_SELECT_DIRECT
                "direct",
#else
                "74HC138",
#endif
                (unsigned long)pixelHz, SPI_DRIVE);
  for (int b = 0; b < NUM_BOARDS; b++) Serial.printf("diag: board %d lt7680 %s, face %d, turn %d\n", b, ok[b] ? "OK" : "FAILED", faceOf[b], rotOf[b]);
  Serial.printf("diag: boot %u-%u ms, STSR=0x%02X\n", t0, t1, readStatus());
#else
  // 以前の起動 (LCD_CS が抜けていた頃の対症療法): 1.5 秒待ってから「流れ」を BOOT_FLOWS 回
  delay(1500);
  loadFaces();
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
  setSpiDrive(SPI_DRIVE);
  for (int f = 0; f < BOOT_FLOWS; f++) flowAll(0x07E0);
  for (int b = 0; b < NUM_BOARDS; b++) { curBoard = b; drawFace(boardFace(curBoard)); }
  curBoard = 0;
  digitalWrite(PIN_BL, HIGH);
#endif
  setupEspnow();
  idleSetup();
  Serial.println("shell ready");
}

// ---- 命令の入力: USB シリアルと ESP-NOW ----
// espnow_bridge (pi5-deck などに挿した ESP32) がブロードキャストする行を、シリアルに打った行と同じ命令として受ける。
// 届いた ESP-NOW の塊を輪に貯め、loop の命令の読み取り (cmdIn) は輪を先に、空ならシリアルを読む。
// 画像やコマを受ける命令 (#U、#R) の本体のバイト列は、今までどおりシリアルからだけ受ける
#ifndef ESPNOW_CHANNEL
#define ESPNOW_CHANNEL 1
#endif
ByteRing<1024> espnowIn;
uint32_t espnowDropped = 0, espnowPackets = 0;

void onEspnowRecv(const esp_now_recv_info_t *info, const uint8_t *data, int n) {
  espnowPackets++;
  if (!espnowIn.pushAll(data, n)) espnowDropped++;
}

class CmdIn : public Stream {
 public:
  int available() override { return espnowIn.size() ? (int)espnowIn.size() : Serial.available(); }
  int read() override { return espnowIn.size() ? espnowIn.pop() : Serial.read(); }
  int peek() override { return espnowIn.size() ? espnowIn.peek() : Serial.peek(); }
  size_t write(uint8_t b) override { return Serial.write(b); }
} cmdIn;

void setupEspnow() {
  WiFi.mode(WIFI_STA);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) { Serial.println("espnow: init failed"); return; }
  esp_now_register_recv_cb(onEspnowRecv);
  uint8_t m[6];
  esp_wifi_get_mac(WIFI_IF_STA, m);
  uint8_t ch = 0;
  wifi_second_chan_t ch2;
  esp_wifi_get_channel(&ch, &ch2);
  Serial.printf("espnow: %02X:%02X:%02X:%02X:%02X:%02X, channel %d (asked %d)\n", m[0], m[1], m[2], m[3], m[4], m[5], ch, ESPNOW_CHANNEL);
}

bool armed = false;
bool bl = true;  // #b で切り替える (手で消したか)

// 何もしていないときにバックライトを消す (idle_backlight.h)。分は NVS の "idle" に残す
static const int IDLE_DEFAULT_MIN = 10;
IdleBacklight idleBl;
bool idleOff = false;

void applyBacklight() { digitalWrite(PIN_BL, (bl && !idleOff) ? HIGH : LOW); }

void idleSetup() {
  prefs.begin("cube", true);
  int m = prefs.getInt("idle", IDLE_DEFAULT_MIN);
  prefs.end();
  idleBl.timeoutMs = (uint32_t)m * 60000;
  idleBl.activity(millis());
  Serial.printf("idle: backlight off after %d min without commands while a USB host is attached (0: never)\n", m);
}

// loop の頭で毎回: ホストの有無を見て、消す・点けるが変わったら反映する
void idleTick() {
  uint32_t now = millis();
  idleBl.host(HWCDC::isPlugged(), now);
  bool o = idleBl.off(now);
  if (o == idleOff) return;
  idleOff = o;
  applyBacklight();
  Serial.printf("idle: backlight %s\n", o ? "off (USB host attached, no commands)" : "on (USB host gone)");
}

// 命令が来た: 待ちをやり直し、消していたら点ける
void idleWake() {
  idleBl.activity(millis());
  if (!idleOff) return;
  idleOff = false;
  applyBacklight();
  Serial.println("idle: backlight on (command)");
}

void loadFaces() {
  prefs.begin("cube", true);
  for (int b = 0; b < NUM_BOARDS; b++) {
    char key[4] = {'f', (char)('0' + b), 0};
    int n = prefs.getInt(key, b % 4);
    faceOf[b] = (n >= 0 && n < NUM_FACES) ? n : b % 4;
    key[0] = 'r';
    rotOf[b] = prefs.getInt(key, 0) & 3;
  }
  prefs.end();
}

// x,n[,r] の x を読んだあと: ',' が来れば面番号 (と回転) を読んで割り当てる。来なければ false
bool assignFace(int x) {
  uint32_t t = millis();
  while (!cmdIn.available() && millis() - t < 50) delay(1);
  if (cmdIn.peek() != ',') return false;
  cmdIn.read();
  long n = cmdIn.parseInt();
  long r = x < NUM_BOARDS ? rotOf[x] : 0;  // 回転を省くと今のまま
  if (cmdIn.peek() == ',') {
    cmdIn.read();
    r = cmdIn.parseInt();
  }
  if (x >= NUM_BOARDS || n < 0 || n >= NUM_FACES || r < 0 || r > 3) {
    Serial.printf("assign: board must be 0-%d, face 0-%d, turn 0-3\n", NUM_BOARDS - 1, NUM_FACES - 1);
    return true;
  }
  faceOf[x] = n;
  rotOf[x] = r;
  char key[4] = {'f', (char)('0' + x), 0};
  prefs.begin("cube", false);
  prefs.putInt(key, n);
  key[0] = 'r';
  prefs.putInt(key, r);
  prefs.end();
  int keep = curBoard;
  curBoard = x;
  Serial.printf("assign: board %d face %ld turn %ld (saved)\n", x, n, r);
  drawFace(boardFace(x));
  curBoard = keep;
  return true;
}

void loop() {
  idleTick();
  if (!cmdIn.available()) { delay(5); return; }
  char c = cmdIn.read();
  idleWake();
  if (c == '#') { armed = true; return; }
  if (c >= '0' && c <= '9' && assignFace(c - '0')) { armed = false; return; }  // x,n (# の有無を問わない)
  if (!armed) return;
  armed = false;
  switch (c) {
    case '0': case '1': case '2':
      if (c - '0' < NUM_BOARDS) { curBoard = c - '0'; Serial.printf("cmd %c: board %d selected\n", c, curBoard); }
      break;
    case 'A': flowAll(0x07E0); Serial.println("cmd A: flow on all boards"); break;
    case 'E': drawFace(boardFace(curBoard)); break;
    case 'H': {  // #H<0-3> LT7680 の SPI の SCK と MOSI の出力の強さ (SPI_DRIVE の説明)
      long cap = cmdIn.parseInt();
      if (cap < 0 || cap > 3) { Serial.println("cmd H: error, 0-3"); break; }
      setSpiDrive(cap);
      Serial.printf("cmd H: SCK and MOSI drive %ld\n", cap);
      break;
    }
    case 'p': {  // #p ESP-NOW で "ping <MAC>" を一斉送信する (電波が届くかの切り分け。espnow_bridge が rx と出す)
      static const uint8_t bc[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
      if (!esp_now_is_peer_exist(bc)) {
        esp_now_peer_info_t peer = {};
        memcpy(peer.peer_addr, bc, 6);
        peer.channel = ESPNOW_CHANNEL;
        esp_now_add_peer(&peer);
      }
      const char msg[] = "ping from the cube";
      Serial.printf("cmd p: %s\n", esp_now_send(bc, (const uint8_t *)msg, sizeof msg - 1) == ESP_OK ? "sent" : "send failed");
      break;
    }
    case 'a': {
        int n = WiFi.scanNetworks();
        Serial.printf("%s %d access points\n", "scan:", n);
        for (int i = 0; i < n && i < 8; i++) Serial.printf("%s   ch %d rssi %d %s\n", "scan:", WiFi.channel(i), WiFi.RSSI(i), WiFi.SSID(i).c_str());
        WiFi.scanDelete();
        esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
      } break;  // #a 周りの Wi-Fi を探して受信の強さを出す (無線とアンテナの確認)
    case 's': showScene(cmdIn.parseInt()); break;  // #s<k> シーン k (microSD) を全基板に描く
    case 'e': exportEarth(cmdIn.parseInt()); break;  // #e<k> 焼き込みの地球をシーン k として microSD に書く
    case 'w': {  // #w<k>,<f> シーン k の面 f を受けて microSD に書く (host/send_scene.py)
      long k = cmdIn.parseInt();
      long f = cmdIn.read() == ',' ? cmdIn.parseInt() : -1;
      receiveSceneFace(k, f);
      break;
    }
    case 'C': cardTest(cmdIn.parseInt()); break;  // #C[<MHz>] microSD (Sense の拡張ボード) を読み書きして速さを測る
    case 'N': {  // 面の割り当て用: 全基板を白地にして、名前 A, B, C と辺の番号 1〜4 を描く (face_label.h)。#E や x,n,r で地球に戻る
      int keep = curBoard;
      for (int b = 0; b < NUM_BOARDS; b++) {
        curBoard = b;
        streamPixels(0, 0, 480, 480, [b](int x, int y) { return faceLabelColor(b, x, y); });
      }
      curBoard = keep;
      Serial.printf("cmd N: boards 0..%d show A..%c, edges 1 top, 2 right, 3 bottom, 4 left\n", NUM_BOARDS - 1, 'A' + NUM_BOARDS - 1);
      break;
    }
    case 'V': verifyFace(boardFace(curBoard)); break;
    case 'S': {
      long mhz = cmdIn.parseInt();
      if (mhz >= 1 && mhz <= 40) pixelHz = mhz * 1000000;
      Serial.printf("cmd S: pixel SPI %lu Hz\n", (unsigned long)pixelHz);
      break;
    }
    case 'F': {  // 選んだ基板に面 n (0〜3) を描く。並べ方を試す用
      long n = cmdIn.parseInt();
      if (n >= 0 && n < NUM_FACES) { Serial.printf("cmd F: board %d face %ld\n", curBoard, n); drawFace(EARTH_QSC480X6[n]); }
      else Serial.println("cmd F: face must be 0-5");
      break;
    }
    case 'I': {  // 選んだ基板だけ初期化し直す (LCM_RESET は全基板共通なので出さない)
      bool ok = initLt7680NoReset();
      Serial.printf("cmd I: board %d lt7680 %s, STSR=0x%02X\n", curBoard, ok ? "OK" : "FAILED", readStatus());
      if (ok) { initPanel(); writeReg(0x12, readReg(0x12) | 0x40); setupMemory(); drawFace(boardFace(curBoard)); }
      break;
    }
    case 'L': {
      long khz = cmdIn.parseInt();
      if (khz >= 10 && khz <= 10000) regHz = khz * 1000;
      Serial.printf("cmd L: register SPI %lu Hz\n", (unsigned long)regHz);
      break;
    }
    case 'K': fillRect(0, 0, 479, 479, 0x0000); Serial.printf("cmd K: board %d black\n", curBoard); break;
    case 'W': fillRect(0, 0, 479, 479, 0xFFFF); Serial.printf("cmd W: board %d white\n", curBoard); break;
    case 'b': bl = !bl; applyBacklight(); Serial.printf("cmd b: backlight %s\n", bl ? "on" : "off"); break;
    case 'i': {  // #i<分> 何もしないときにバックライトを消すまで (USB ホストがいるときだけ、0 で消さない)。#i だけなら今の値
      if (!isdigit(cmdIn.peek())) { Serial.printf("cmd i: %lu min, host %s\n", (unsigned long)(idleBl.timeoutMs / 60000), idleBl.hostConnected(millis()) ? "attached" : "absent"); break; }
      long m = cmdIn.parseInt();
      if (m < 0 || m > 1440) { Serial.println("cmd i: error, 0-1440"); break; }
      idleBl.timeoutMs = (uint32_t)m * 60000;
      prefs.begin("cube", false);
      prefs.putInt("idle", m);
      prefs.end();
      Serial.printf("cmd i: backlight off after %ld min without commands while a USB host is attached (saved)\n", m);
      break;
    }
#ifdef BOARD_SELECT_DIRECT  // 74HC138 経由では CS を 1 本ずつ浮かせられない
    case 'P': {
      // 基板側のプルアップ/プルダウンの有無: 内蔵プルダウンで 1 なら外部プルアップ、内蔵プルアップで 0 なら外部プルダウン。
      // 他の 2 本は既定の待機状態 (CS High、SCLK/DIN Low) に保ったまま 1 本ずつ調べる
      const int pins[3] = {PIN_LCD_CS, PIN_PANEL_SCK, PIN_PANEL_SDA};
      const char *names[3] = {"LCD_CS", "LCD_SCLK", "LCD_DIN"};
      for (int k = 0; k < 3; k++) {
        pinMode(pins[k], INPUT_PULLDOWN);
        delay(5);
        int withDown = digitalRead(pins[k]);
        pinMode(pins[k], INPUT_PULLUP);
        delay(5);
        int withUp = digitalRead(pins[k]);
        pinMode(pins[k], OUTPUT);
        digitalWrite(pins[k], pins[k] == PIN_LCD_CS ? HIGH : LOW);
        Serial.printf("cmd P: %s pulldown->%d pullup->%d (%s)\n", names[k], withDown, withUp,
                      withDown ? "external pull-up" : !withUp ? "external pull-down" : "no external pull");
      }
      break;
    }
#endif
    case 'Q': {
      // 1 行 "x y w h color" (10 進、color は RGB565) を読んで四角形を塗る。ISS の軌跡など、母艦からの重ね描き用
      String line = Serial.readStringUntil('\n');
      int x, y, w, h, col;
      if (sscanf(line.c_str(), "%d %d %d %d %d", &x, &y, &w, &h, &col) == 5 && x >= 0 && y >= 0 && x + w <= 480 && y + h <= 480 && w > 0 && h > 0) {
        fillRect(x, y, x + w - 1, y + h - 1, (uint16_t)col);
      } else {
        Serial.printf("cmd Q: bad line '%s'\n", line.c_str());
      }
      break;
    }
    case 'D': {  // #D<秒>[,<ラベル 0/1>[,<基板あたりの飛行機>]] 架空の飛行機と船を動かす (既定 30 秒、ラベル無し、5 機)
      long sec = cmdIn.parseInt();
      bool labels = cmdIn.peek() == ',' && (cmdIn.read(), cmdIn.parseInt() == 1);
      long planes = cmdIn.peek() == ',' ? (cmdIn.read(), cmdIn.parseInt()) : 5;
      demoMovers(sec > 0 ? sec : 30, labels, constrain(planes, 0, 200));
      break;
    }
    case 'G': {  // #G<秒>[,<ラベル 0/1>[,<基板あたりの飛行機>[,<切り替えを待つ 0/1、既定 1>[,<コマの間のレジスタ MHz、既定 10>]]]] #D のダブルバッファ版
      long sec = cmdIn.parseInt();
      bool labels = cmdIn.peek() == ',' && (cmdIn.read(), cmdIn.parseInt() == 1);
      long planes = cmdIn.peek() == ',' ? (cmdIn.read(), cmdIn.parseInt()) : 5;
      bool vsync = cmdIn.peek() == ',' ? (cmdIn.read(), cmdIn.parseInt() != 0) : true;
      long mhz = cmdIn.peek() == ',' ? (cmdIn.read(), cmdIn.parseInt()) : 10;
      demoDouble(sec > 0 ? sec : 30, labels, constrain(planes, 0, 200), vsync, constrain(mhz, 1, 10) * 1000000);  // 20MHz では状態の読みが化けた
      break;
    }
    case 'U': receiveFace(cmdIn.parseInt()); break;  // #U<面> 面の画像を受け取る
    case 'u': {  // 送られてきた面の画像を捨てて、焼き込みの地球に戻す
      for (int f = 0; f < NUM_FACES; f++) { free(faceOverride[f]); faceOverride[f] = nullptr; }
      for (int b = 0; b < NUM_BOARDS; b++) { curBoard = b; drawToPage(0); showPage(0); drawFace(boardFace(b)); }
      curBoard = 0;
      Serial.println("cmd u: built-in faces");
      break;
    }
    case 'R': {  // #R<基板>,<コマ> パラパラ漫画の 1 コマを受ける
      long b = cmdIn.parseInt();
      long k = cmdIn.peek() == ',' ? (cmdIn.read(), cmdIn.parseInt()) : 0;
      receivePage(b, k);
      break;
    }
    case 'M': {  // #M<ミリ秒>[,<コマ数>] パラパラ漫画を再生する
      long ms = cmdIn.parseInt();
      long n = cmdIn.peek() == ',' ? (cmdIn.read(), cmdIn.parseInt()) : 0;
      playFlip(ms > 0 ? ms : 200, n);
      break;
    }
    case 'Z': probePages(); break;  // 表示用メモリのページがどこまで別々か確かめる (選んだ基板)
    case 'Y': { long sec = cmdIn.parseInt(); retentionTest(sec > 0 ? sec : 120); break; }  // 表示していないページが時間で化けるか
    case 'X': dumpPage(cmdIn.parseInt()); break;  // ページを丸ごと読み返してシリアルに出す (選んだ基板)
    case 'B': pageSelfTest(); break;  // ページの切り替えと LT7680 の中でのコピーを確かめる (選んだ基板)
    case 'T': {  // #T<コマ数>,<大きさ> 印を動かす速さを測る (既定 200 コマ、12 画素)
      long n = cmdIn.parseInt();
      long sz = cmdIn.peek() == ',' ? (cmdIn.read(), cmdIn.parseInt()) : 12;
      if (n <= 0) n = 200;
      if (sz < 1 || sz > 64) sz = 12;
      benchMarker(n, sz);
      break;
    }
    case 'r': Serial.printf("cmd r: board %d STSR=0x%02X CCR=0x%02X DPCR=0x%02X, espnow %lu packets %lu dropped\n", curBoard, readStatus(), readReg(0x01), readReg(0x12), (unsigned long)espnowPackets, (unsigned long)espnowDropped); break;
    default: Serial.printf("cmd %c: unknown\n", c); break;
  }
  idleBl.activity(millis());  // #G のような長い命令は、終わってから待ち始める
}
