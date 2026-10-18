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
// 命令 (先頭に '#'): n<0-2> 基板を選ぶ、0 選んだ基板の流れ、A 全基板の流れ、E 地球、K/W 黒/白、r 状態、b バックライト
// 面の割り当て (先頭の '#' は無くてよい): x,n で基板 x に面 n (0-5) を割り当てて描く。不揮発領域に保存し、再起動後も使う

#include "earth_qsc480x6.h"
#include <Preferences.h>
#include <SPI.h>

#ifndef NUM_BOARDS
#define NUM_BOARDS 1
#endif

// QSC の面: 0〜3 は側面 (面 0 は東京 139.767 度を中心に、経度 90 度おきに東へ)、4 は北極、5 は南極。
// 立方体の外から見て、面 k+1 は面 k の右隣、北極は面 0 の上、南極は面 0 の下につながる
#define NUM_FACES 6
// 基板ごとの面。既定は基板 b に側面 b、x,n 命令で変えて不揮発領域 ("cube" の "f<b>") に保存する
int faceOf[NUM_BOARDS];
Preferences prefs;
// (関数にすると Arduino の自動プロトタイプがここに入り、後ろの enum より前に来てビルドが壊れる)
#define boardFace(b) (EARTH_QSC480X6[faceOf[b]])

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

// 74HC138 のアドレスを置く。アドレスを変える瞬間に隣の出力が ns 単位で落ちることがあるが、
// クロックが止まっている間の CS のパルスは LT7680 も ST7701S も無視する
void selectLine(Sel s) {
#ifdef BOARD_SELECT_DIRECT
  digitalWrite(PIN_SCS, s == SEL_LT ? LOW : HIGH);
  digitalWrite(PIN_LCD_CS, s == SEL_LCD ? LOW : HIGH);
#else
  int code = (s == SEL_NONE) ? 7 : (s == SEL_LT ? curBoard : 3 + curBoard);
  for (int i = 0; i < 3; i++) digitalWrite(PIN_ADDR[i], (code >> i) & 1);
#endif
}

void selectSetup() {
#ifdef BOARD_SELECT_DIRECT
  pinMode(PIN_SCS, OUTPUT);
  pinMode(PIN_LCD_CS, OUTPUT);
#else
  for (int i = 0; i < 3; i++) pinMode(PIN_ADDR[i], OUTPUT);
#endif
  selectLine(SEL_NONE);
}

SPISettings lt(1000000, MSBFIRST, SPI_MODE3);

// ---- LT7680 (4 線 SPI、1 回 16 クロック、先頭 8 ビットが前置き) ----

uint8_t xfer16(uint8_t prefix, uint8_t data) {
  SPI.beginTransaction(lt);
  selectLine(SEL_LT);
  SPI.transfer(prefix);
  uint8_t r = SPI.transfer(data);
  selectLine(SEL_NONE);
  SPI.endTransaction();
  return r;
}

void writeReg(uint8_t reg, uint8_t val) {
  xfer16(0x00, reg);
  xfer16(0x80, val);
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
  writeReg(0xE0, 0x29);
  writeReg(0xE1, 0x03);
  // SDRAM のリフレッシュ間隔。LCD.cpp の SDRAM_initail と同じ (64ms / 8192 行 / (1000/60) - 2 = 486)。
  // 以前の 0x61A (1562) では、書いた画素が数十秒で 1 ビットずつ化けていった
  writeReg(0xE2, SDRAM_ITV & 0xFF);
  writeReg(0xE3, SDRAM_ITV >> 8);
  writeReg(0xE4, 0x05);
  if (!waitFor("display RAM ready", 1000, [] { return (readStatus() & 0x04) != 0; })) return false;

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

// 選んだ基板の表示用メモリに face を書く (64 バイトのバースト、480x480 で約 4.1 秒)
void drawFace(const uint16_t *face) {
  writeReg16(0x56, 0);
  writeReg16(0x58, 0);
  writeReg16(0x5A, 480);
  writeReg16(0x5C, 480);
  writeReg16(0x5F, 0);
  writeReg16(0x61, 0);
  xfer16(0x00, 0x04);
  SPISettings fast(pixelHz, MSBFIRST, SPI_MODE3);
  uint8_t buf[64];
  int n = 0;
  uint32_t t0 = millis();
  for (uint32_t i = 0; i < 480u * 480u; i++) {
    uint16_t c = face[i];
    buf[n++] = c & 0xFF;
    buf[n++] = c >> 8;
    if (n == sizeof(buf)) {
      while (readStatus() & 0x80) {
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
  Serial.printf("board %d: face written in %lu ms\n", curBoard, (unsigned long)(millis() - t0));
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
    uint16_t got = lo | (hi << 8);
    if (got != face[i] && bad++ < 5) {
      Serial.printf("verify NG at (%lu,%lu): got 0x%04X want 0x%04X\n", (unsigned long)(i % 480),
                    (unsigned long)(i / 480), got, face[i]);
    }
  }
  Serial.printf("board %d: verify %lu bad pixels of %u in %lu ms\n", curBoard, (unsigned long)bad, 480u * 480u,
                (unsigned long)(millis() - t0));
  return bad;
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
  selectSetup();
  pinMode(PIN_PANEL_SCK, OUTPUT);
  digitalWrite(PIN_PANEL_SCK, LOW);
  pinMode(PIN_PANEL_SDA, OUTPUT);
  digitalWrite(PIN_PANEL_SDA, LOW);
  pinMode(PIN_BL, OUTPUT);
  digitalWrite(PIN_BL, LOW);
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
  digitalWrite(PIN_RESET, LOW);  // LCM_RESET は全基板で共通
  delay(LT_RESET_HOLD_MS);
  digitalWrite(PIN_RESET, HIGH);
  delay(100);
  bool ok[NUM_BOARDS];
  for (int b = 0; b < NUM_BOARDS; b++) {
    curBoard = b;
    ok[b] = initLt7680NoReset();
    initPanel();
    writeReg(0x12, readReg(0x12) | 0x40);  // 表示オン
    setupMemory();
    drawFace(boardFace(curBoard));
  }
  curBoard = 0;
  digitalWrite(PIN_BL, HIGH);
  uint32_t t1 = millis();
  while (millis() < 3000) delay(10);  // シリアルの読み手が付いてから報告する
  Serial.printf("reset reason: %d, boards: %d, select: %s, pixel SPI %lu Hz\n", (int)esp_reset_reason(), NUM_BOARDS,
#ifdef BOARD_SELECT_DIRECT
                "direct",
#else
                "74HC138",
#endif
                (unsigned long)pixelHz);
  for (int b = 0; b < NUM_BOARDS; b++) Serial.printf("diag: board %d lt7680 %s, face %d\n", b, ok[b] ? "OK" : "FAILED", faceOf[b]);
  Serial.printf("diag: boot %u-%u ms, STSR=0x%02X\n", t0, t1, readStatus());
#else
  // 以前の起動 (LCD_CS が抜けていた頃の対症療法): 1.5 秒待ってから「流れ」を BOOT_FLOWS 回
  delay(1500);
  loadFaces();
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
  for (int f = 0; f < BOOT_FLOWS; f++) flowAll(0x07E0);
  for (int b = 0; b < NUM_BOARDS; b++) { curBoard = b; drawFace(boardFace(curBoard)); }
  curBoard = 0;
  digitalWrite(PIN_BL, HIGH);
#endif
  Serial.println("shell ready");
}

bool armed = false;
bool bl = true;

void loadFaces() {
  prefs.begin("cube", true);
  for (int b = 0; b < NUM_BOARDS; b++) {
    char key[4] = {'f', (char)('0' + b), 0};
    int n = prefs.getInt(key, b % 4);
    faceOf[b] = (n >= 0 && n < NUM_FACES) ? n : b % 4;
  }
  prefs.end();
}

// x,n の x を読んだあと: ',' が来れば面番号を読んで割り当てる。来なければ false
bool assignFace(int x) {
  uint32_t t = millis();
  while (!Serial.available() && millis() - t < 50) delay(1);
  if (Serial.peek() != ',') return false;
  Serial.read();
  long n = Serial.parseInt();
  if (x >= NUM_BOARDS || n < 0 || n >= NUM_FACES) {
    Serial.printf("assign: board must be 0-%d, face 0-%d\n", NUM_BOARDS - 1, NUM_FACES - 1);
    return true;
  }
  faceOf[x] = n;
  char key[4] = {'f', (char)('0' + x), 0};
  prefs.begin("cube", false);
  prefs.putInt(key, n);
  prefs.end();
  int keep = curBoard;
  curBoard = x;
  Serial.printf("assign: board %d face %ld (saved)\n", x, n);
  drawFace(boardFace(x));
  curBoard = keep;
  return true;
}

void loop() {
  if (!Serial.available()) { delay(5); return; }
  char c = Serial.read();
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
    case 'V': verifyFace(boardFace(curBoard)); break;
    case 'S': {
      long mhz = Serial.parseInt();
      if (mhz >= 1 && mhz <= 40) pixelHz = mhz * 1000000;
      Serial.printf("cmd S: pixel SPI %lu Hz\n", (unsigned long)pixelHz);
      break;
    }
    case 'F': {  // 選んだ基板に面 n (0〜3) を描く。並べ方を試す用
      long n = Serial.parseInt();
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
    case 'K': fillRect(0, 0, 479, 479, 0x0000); Serial.printf("cmd K: board %d black\n", curBoard); break;
    case 'W': fillRect(0, 0, 479, 479, 0xFFFF); Serial.printf("cmd W: board %d white\n", curBoard); break;
    case 'b': bl = !bl; digitalWrite(PIN_BL, bl); Serial.printf("cmd b: backlight %s\n", bl ? "on" : "off"); break;
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
    case 'r': Serial.printf("cmd r: board %d STSR=0x%02X CCR=0x%02X DPCR=0x%02X\n", curBoard, readStatus(), readReg(0x01), readReg(0x12)); break;
    default: Serial.printf("cmd %c: unknown\n", c); break;
  }
}
