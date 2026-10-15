// lt7680_earth.ino
//
// 四角い地球 大型版の最初の表示: QSC 投影の地球の 1 面 (480x480、中心は東経 139.767 度) を
// LT7680A-R の表示用メモリに書いて ER-TFT040-3 に映す。lt7680_shell の命令はそのまま残してある
// (E で地球の面を書き直す)。
//
// 起動の手順 (2026-10-15 の仮説検証の結果):
//   LT7680 のリセットと初期化 → 表示オン → 主画面の設定 → 黒で塗る →
//   パネルの初期化列を 2 回 (XIAO の起動中にパネル用 SCLK が浮くと 1 回では約 3 割しか通らない。
//   2 回で 8/8) → 地球の面を書く → バックライト
// 画素は 64 バイトのバーストで 1MHz。480x480x2 バイトで約 4.1 秒。
// 面の生成: make_qsc_faces.py blue_marble_2002.jpg earth_qsc480.h --lon0 139.767 --count 1 --step 30 --name EARTH_QSC480 --size 480

#include "earth_qsc480.h"
#include <SPI.h>

static const int PIN_SCS    = D0;
static const int PIN_RESET  = D1;
static const int PIN_LCD_CS = D2;
static const int PIN_BL     = D3;
static const int PIN_SCK    = D8;
static const int PIN_MISO   = D9;
static const int PIN_MOSI   = D10;
static const int PIN_PANEL_SCK = D4;  // CON1 19 LCD_SCLK
static const int PIN_PANEL_SDA = D5;  // CON1 18 LCD_DIN

SPISettings lt(1000000, MSBFIRST, SPI_MODE3);

// ---- LT7680 (4 線 SPI、1 回 16 クロック、先頭 8 ビットが前置き) ----

uint8_t xfer16(uint8_t prefix, uint8_t data) {
  SPI.beginTransaction(lt);
  digitalWrite(PIN_SCS, LOW);
  SPI.transfer(prefix);
  uint8_t r = SPI.transfer(data);
  digitalWrite(PIN_SCS, HIGH);
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
      Serial.printf("TIMEOUT waiting for %s\n", what);
      return false;
    }
    delay(1);
  }
  Serial.printf("ok: %s (%lu ms)\n", what, (unsigned long)(millis() - t0));
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
  digitalWrite(PIN_LCD_CS, LOW);
  panelBit(dc);
  for (int i = 7; i >= 0; i--) panelBit((v >> i) & 1);
  digitalWrite(PIN_LCD_CS, HIGH);
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

bool initLt7680() {
  digitalWrite(PIN_RESET, LOW);  // LCD.cpp の HW_Reset は 100ms
  delay(LT_RESET_HOLD_MS);
  digitalWrite(PIN_RESET, HIGH);
  delay(200);
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
  writeReg(0xE2, 0x1A);
  writeReg(0xE3, 0x06);
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
  Serial.printf("display regs: 10=0x%02X 12=0x%02X 13=0x%02X 14=0x%02X 1A=0x%02X 1B=0x%02X\n",
                readReg(0x10), readReg(0x12), readReg(0x13), readReg(0x14), readReg(0x1A), readReg(0x1B));
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
  uint32_t t0 = micros();
  writeReg(0x76, 0xE0);  // 四角形を塗りつぶしで描く
  waitDrawDone();
  (void)t0;
}

#ifndef BOOT_SERIAL_DELAY_MS
#define BOOT_SERIAL_DELAY_MS 1500  // シリアルの読み手が付くのを待つ時間。実験 E4 では 0 にする
#endif
#ifndef BOOT_FLOWS
#define BOOT_FLOWS 2
#endif
#ifndef BOOT_PANEL_INITS
#define BOOT_PANEL_INITS 2
#endif
#ifndef BOOT_FLOW_GAP_MS
#define BOOT_FLOW_GAP_MS 0
#endif
#ifndef BOOT_SETTLE_MS
#define BOOT_SETTLE_MS 0  // 起動からパネルを含めた初期化までの待ち
#endif

esp_reset_reason_t why = ESP_RST_UNKNOWN;
bool powerOn = false;

static const uint32_t PIXEL_SPI_HZ = 1000000;

// 表示用メモリの (0,0) から 480x480 の面を書く。前置き 0x80 を 1 回送った後に 64 バイト続けて送る
void drawEarth() {
  writeReg16(0x56, 0);
  writeReg16(0x58, 0);
  writeReg16(0x5A, 480);
  writeReg16(0x5C, 480);
  writeReg16(0x5F, 0);
  writeReg16(0x61, 0);
  xfer16(0x00, 0x04);
  SPISettings fast(PIXEL_SPI_HZ, MSBFIRST, SPI_MODE3);
  uint8_t buf[64];
  int n = 0;
  uint32_t t0 = millis();
  const uint16_t *face = EARTH_QSC480[0];
  for (uint32_t i = 0; i < 480u * 480u; i++) {
    uint16_t c = face[i];
    buf[n++] = c & 0xFF;
    buf[n++] = c >> 8;
    if (n == sizeof(buf)) {
      while (readStatus() & 0x80) {
      }
      SPI.beginTransaction(fast);
      digitalWrite(PIN_SCS, LOW);
      SPI.transfer(0x80);
      SPI.writeBytes(buf, n);
      digitalWrite(PIN_SCS, HIGH);
      SPI.endTransaction();
      n = 0;
    }
  }
  Serial.printf("earth: face 0 written in %lu ms\n", (unsigned long)(millis() - t0));
}

#include "soc/io_mux_reg.h"
#include "soc/gpio_reg.h"
#include "soc/gpio_periph.h"
// setup の先頭でピンに触る前に、リセット直後の IO_MUX の設定 (プルアップ/ダウン、入力有効) と入力の値を控える
uint32_t bootMux[8], bootIn;
void snapshotBootPins() {
  const int pins[8] = {1, 2, 3, 4, 5, 6, 7, 9};  // D0 D1 D2 D3 D4 D5 D8 D10
  for (int i = 0; i < 8; i++) bootMux[i] = REG_READ(GPIO_PIN_MUX_REG[pins[i]]);
  bootIn = REG_READ(GPIO_IN_REG);
}
void printBootPins() {
  const int pins[8] = {1, 2, 3, 4, 5, 6, 7, 9};
  const char *names[8] = {"D0", "D1", "D2", "D3", "D4", "D5", "D8", "D10"};
  for (int i = 0; i < 8; i++)
    Serial.printf("bootpin %s gpio%d: mux=0x%08lx wpu=%d wpd=%d ie=%d in=%d\n", names[i], pins[i], (unsigned long)bootMux[i],
                  (int)((bootMux[i] >> FUN_PU_S) & 1), (int)((bootMux[i] >> FUN_PD_S) & 1), (int)((bootMux[i] >> FUN_IE_S) & 1),
                  (int)((bootIn >> pins[i]) & 1));
}

void setup() {
  snapshotBootPins();
  // LCM_RESET は基板にプルアップが無く、浮くとノイズで LT7680 がリセットを繰り返す。
  // 起動の最初に High に固定する
  pinMode(PIN_RESET, OUTPUT_OPEN_DRAIN);
  gpio_pullup_en((gpio_num_t)PIN_RESET);
  digitalWrite(PIN_RESET, HIGH);
  pinMode(PIN_SCS, OUTPUT);
  digitalWrite(PIN_SCS, HIGH);
  pinMode(PIN_LCD_CS, OUTPUT);
  digitalWrite(PIN_LCD_CS, HIGH);
  // パネル用の SCLK と DIN も、起動したらすぐ出力にする。電源投入でない起動ではパネルを初期化しないが、
  // 後から #s や #p を送れるようにするため (以前は初期化のときだけ出力にしていて、命令が出ていなかった)
  pinMode(PIN_PANEL_SCK, OUTPUT);
  digitalWrite(PIN_PANEL_SCK, LOW);
  pinMode(PIN_PANEL_SDA, OUTPUT);
  digitalWrite(PIN_PANEL_SDA, LOW);
  pinMode(PIN_BL, OUTPUT);
  digitalWrite(PIN_BL, LOW);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(BOOT_SERIAL_DELAY_MS);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);

  // 起動の正常系 (2026-10-15 の試行錯誤から):
  // 命令として実行した「LT7680 のリセットと初期化 → 表示オン → 主画面の設定と塗りつぶし →
  // パネルのソフトリセット → パネルの初期化」は、起動から 8〜10 秒後なら 21 回中 18 回映った。
  // 同じ関数を起動直後 (約 1.5 秒) に呼ぶと、ほとんど映らなかった。順番、LT7680 の再始動から
  // パネルの初期化までの待ち、線の浮き、バックライトの切り替えは差を生まなかったので、
  // 起動からの経過時間を合わせる
  why = esp_reset_reason();
  powerOn = (why == ESP_RST_POWERON);
  Serial.printf("reset reason: %d (%s)\n", (int)why, powerOn ? "power on" : "not power on");
  printBootPins();
  delay(BOOT_SETTLE_MS);
  // 実験 E15: LT7680 のリセットを含む流れ全体を BOOT_FLOWS 回、BOOT_FLOW_GAP_MS 空けて走らせる
  for (int f = 0; f < BOOT_FLOWS; f++) {
    if (f > 0) delay(BOOT_FLOW_GAP_MS);
    bool ok = initLt7680();
    Serial.printf("lt7680: %s\n", ok ? "INIT OK" : "INIT FAILED");
    writeReg(0x12, readReg(0x12) | 0x40);  // 表示オン
    setupMemory();
    // 起動時は緑で塗る。カメラの判定で、机 (橙) とも黒いパネル (青に写る) とも重ならない色
    fillRect(0, 0, 479, 479, 0x07E0);
    for (int k = 0; k < BOOT_PANEL_INITS; k++) {
      if (k > 0) delay(200);
      resetAndInitPanel();
    }
    Serial.printf("panel: SWRESET + init x%d (flow %d of %d)\n", BOOT_PANEL_INITS, f + 1, BOOT_FLOWS);
  }
  drawEarth();
  digitalWrite(PIN_BL, HIGH);
  Serial.println("shell ready");
  Serial.println("backlight on");
}

static const uint16_t COLORS[] = {0xF800, 0x07E0, 0x001F, 0xFFFF, 0x0000};
static const char *NAMES[] = {"red", "green", "blue", "white", "black"};
int colorIdx = 1;  // 起動時の色 (緑)
bool bl = true;

bool armed = false;
char pendingCmd = 0;  // 引数を 1 文字取る命令 (G) の待ち

// 実験 E1: LT7680 をリセットに保ってパネルのクロックを gapMs 止めてから、#0 と同じ手順を行う
void gapThenReinit(uint32_t gapMs) {
  digitalWrite(PIN_RESET, LOW);
  delay(gapMs);
  bool ok = initLt7680();  // この中で 100ms のリセットと PLL、SDRAM
  writeReg(0x12, readReg(0x12) | 0x40);
  setupMemory();
  fillRect(0, 0, 479, 479, COLORS[colorIdx]);
  resetAndInitPanel();
  Serial.printf("cmd G: clock gap %lu ms, lt7680 %s, panel SWRESET + init\n", (unsigned long)gapMs, ok ? "OK" : "FAILED");
}

// 実験 F: 起動時と同じ条件を命令で模倣する。variant のビット: 1=パネル 3 本と LCM_RESET/LCM_SCS を 3 秒浮かせる
// (0 なら SCLK だけ)、2=その間と初期化中はバックライトを消す、4=初期化の直後に地球を描かない
void bootLikeFlow(int variant) {
  bool floatAll = !(variant & 1);
  bool blOff = !(variant & 2);
  bool draw = !(variant & 4);
  uint32_t t0 = millis();
  if (blOff) digitalWrite(PIN_BL, LOW);
  pinMode(PIN_PANEL_SCK, INPUT);
  if (floatAll) {
    pinMode(PIN_PANEL_SDA, INPUT);
    pinMode(PIN_LCD_CS, INPUT);
    pinMode(PIN_SCS, INPUT);
    gpio_pullup_dis((gpio_num_t)PIN_RESET);
    pinMode(PIN_RESET, INPUT);
  }
  delay(3000);
  pinMode(PIN_RESET, OUTPUT_OPEN_DRAIN);
  gpio_pullup_en((gpio_num_t)PIN_RESET);
  digitalWrite(PIN_RESET, HIGH);
  pinMode(PIN_SCS, OUTPUT);
  digitalWrite(PIN_SCS, HIGH);
  pinMode(PIN_LCD_CS, OUTPUT);
  digitalWrite(PIN_LCD_CS, HIGH);
  pinMode(PIN_PANEL_SCK, OUTPUT);
  digitalWrite(PIN_PANEL_SCK, LOW);
  pinMode(PIN_PANEL_SDA, OUTPUT);
  digitalWrite(PIN_PANEL_SDA, LOW);
  delay(1500);
  bool ok = initLt7680();
  writeReg(0x12, readReg(0x12) | 0x40);
  setupMemory();
  fillRect(0, 0, 479, 479, 0x07E0);
  resetAndInitPanel();
  delay(200);
  resetAndInitPanel();
  if (draw) drawEarth();
  digitalWrite(PIN_BL, HIGH);
  Serial.printf("cmd F%d: float %s, bl %s, draw %s, lt7680 %s, init twice, took %lu ms\n", variant, floatAll ? "all" : "sclk",
                blOff ? "off" : "on", draw ? "yes" : "no", ok ? "OK" : "FAILED", (unsigned long)(millis() - t0));
}

void loop() {
  if (!Serial.available()) { delay(5); return; }
  char c = Serial.read();
  if (pendingCmd == 'm') {
    pendingCmd = 0;
    if (c < '0' || c > '5') return;
    // 実験 E11: SCLK を 5 秒浮かせた直後に、候補の手順を挟んでから #0 と同じ初期化
    pinMode(PIN_PANEL_SCK, INPUT);
    delay(5000);
    pinMode(PIN_PANEL_SCK, OUTPUT);
    digitalWrite(PIN_PANEL_SCK, LOW);
    switch (c) {
      case '1':  // CS を SCLK Low のまま 16 回上げ下げ
        for (int i = 0; i < 16; i++) { digitalWrite(PIN_LCD_CS, LOW); delayMicroseconds(20); digitalWrite(PIN_LCD_CS, HIGH); delayMicroseconds(20); }
        break;
      case '2':  // ソフトリセット 3 回
        for (int i = 0; i < 3; i++) { panelCmd(0x01); delay(150); }
        break;
      case '3':  // 2 秒待つ
        delay(2000);
        break;
      case '5':  // CS High のまま SCLK を 32 回打ち、その後 CS を上げ下げ
        for (int i = 0; i < 32; i++) { digitalWrite(PIN_PANEL_SCK, HIGH); delayMicroseconds(2); digitalWrite(PIN_PANEL_SCK, LOW); delayMicroseconds(2); }
        digitalWrite(PIN_LCD_CS, LOW); delayMicroseconds(20); digitalWrite(PIN_LCD_CS, HIGH); delayMicroseconds(20);
        break;
    }
    gapThenReinit(100);
    if (c == '4') { delay(200); resetAndInitPanel(); }  // 初期化列を 2 回
    Serial.printf("cmd m%c done\n", c);
    return;
  }
  if (pendingCmd == 'F') {
    pendingCmd = 0;
    if (c >= '0' && c <= '7') bootLikeFlow(c - '0');
    return;
  }
  if (pendingCmd == 'G') {
    pendingCmd = 0;
    static const uint32_t GAPS[] = {100, 1000, 2000, 4000, 8000, 16000};
    if (c >= '0' && c <= '5') gapThenReinit(GAPS[c - '0']);
    return;
  }
  if (c == '#') { armed = true; return; }
  if (!armed) return;
  armed = false;
  switch (c) {
    case 'G': pendingCmd = 'G'; break;
    case 'F': pendingCmd = 'F'; break;
    case 'E': drawEarth(); break;
    case 'm': pendingCmd = 'm'; break;
    case 'x':
    case 'y':
    case 'z': {
      // 実験 E10: 1 本だけ 5 秒浮かせてから #0 と同じ初期化。x=LCD_CS、y=SCLK、z=DIN。他の 2 本は駆動したまま
      int pin = (c == 'x') ? PIN_LCD_CS : (c == 'y') ? PIN_PANEL_SCK : PIN_PANEL_SDA;
      pinMode(pin, INPUT);
      delay(5000);
      pinMode(pin, OUTPUT);
      digitalWrite(pin, (pin == PIN_LCD_CS) ? HIGH : LOW);
      Serial.printf("cmd %c: floated %s 5 s, then\n", c, (c == 'x') ? "LCD_CS" : (c == 'y') ? "SCLK" : "DIN");
      gapThenReinit(100);
      break;
    }
    case 'N':
      // 仮説の検証: 浮いた線から入ったでたらめな命令が「全画素オフ 0x22 / 全画素オン 0x23」だとすれば、
      // 通常表示モード 0x13 (とアイドル解除 0x38) を送るだけで戻るはず
      panelCmd(0x13);
      panelCmd(0x38);
      Serial.println("cmd N: NORON + IDMOFF sent");
      break;
    case 'C': {
      // LCD_CS を入力にしたときの読み値。内部プルアップで 1 にならなければ、基板側に強いプルダウンがある
      pinMode(PIN_LCD_CS, INPUT_PULLUP); delayMicroseconds(100); int up = digitalRead(PIN_LCD_CS);
      pinMode(PIN_LCD_CS, INPUT); delayMicroseconds(100); int none = digitalRead(PIN_LCD_CS);
      pinMode(PIN_LCD_CS, INPUT_PULLDOWN); delayMicroseconds(100); int down = digitalRead(PIN_LCD_CS);
      pinMode(PIN_LCD_CS, OUTPUT); digitalWrite(PIN_LCD_CS, HIGH);
      pinMode(PIN_PANEL_SCK, INPUT_PULLUP); delayMicroseconds(100); int sup = digitalRead(PIN_PANEL_SCK);
      pinMode(PIN_PANEL_SCK, INPUT_PULLDOWN); delayMicroseconds(100); int sdown = digitalRead(PIN_PANEL_SCK);
      pinMode(PIN_PANEL_SCK, OUTPUT); digitalWrite(PIN_PANEL_SCK, LOW);
      Serial.printf("cmd C: LCD_CS pullup=%d none=%d pulldown=%d | SCLK pullup=%d pulldown=%d\n", up, none, down, sup, sdown);
      break;
    }
    case 'A':
    case 'B': {
      // 実験 E5/E6: パネル線を 5 秒浮かせてから、すぐに #0 と同じ初期化を行う。
      // A は 3 本とも浮かせる。B は LCD_CS だけ内部プルアップで High に保つ
      pinMode(PIN_LCD_CS, c == 'B' ? INPUT_PULLUP : INPUT);
      pinMode(PIN_PANEL_SCK, INPUT);
      pinMode(PIN_PANEL_SDA, INPUT);
      delay(5000);
      pinMode(PIN_LCD_CS, OUTPUT);
      digitalWrite(PIN_LCD_CS, HIGH);
      pinMode(PIN_PANEL_SCK, OUTPUT);
      digitalWrite(PIN_PANEL_SCK, LOW);
      pinMode(PIN_PANEL_SDA, OUTPUT);
      digitalWrite(PIN_PANEL_SDA, LOW);
      Serial.printf("cmd %c: panel lines floated 5 s%s, then\n", c, c == 'B' ? " (LCD_CS pulled up)" : "");
      gapThenReinit(100);
      break;
    }
    case 'R':
      // 実験 E7: USB の再列挙を伴わないソフト再起動。起動の流れがそのまま走る
      Serial.println("cmd R: esp_restart");
      delay(50);
      esp_restart();
      break;
    case 'l': {
      bool ok = initLt7680();
      writeReg(0x12, readReg(0x12) | 0x40);
      setupMemory();
      fillRect(0, 0, 479, 479, COLORS[colorIdx]);
      Serial.printf("cmd l: lt7680 %s, filled %s\n", ok ? "INIT OK" : "INIT FAILED", NAMES[colorIdx]);
      break;
    }
    case 'p': sendPanelInit(); Serial.println("cmd p: panel init sent"); break;
    case 's': {
      const uint8_t page0[] = {0x77, 0x01, 0x00, 0x00, 0x00};
      panelCmd(0xFF, page0, sizeof(page0));
      panelCmd(0x01);
      delay(120);
      Serial.println("cmd s: panel SWRESET sent");
      break;
    }
    case 'i': panelCmd(0x21); Serial.println("cmd i: INVON"); break;
    case 'n': panelCmd(0x20); Serial.println("cmd n: INVOFF"); break;
    case 'f':
      colorIdx = (colorIdx + 1) % 5;
      fillRect(0, 0, 479, 479, COLORS[colorIdx]);
      Serial.printf("cmd f: filled %s\n", NAMES[colorIdx]);
      break;
    case 'Y':
    case 'Z': {
      // 切り分け: XIAO の再起動中と同じく、パネル用の線を 5 秒浮かせる。
      // Y は LCD_CS (D2) だけ内部プルアップで High に保つ。Z は 3 本とも完全に浮かせる
      pinMode(PIN_LCD_CS, c == 'Y' ? INPUT_PULLUP : INPUT);
      pinMode(PIN_PANEL_SCK, INPUT);
      pinMode(PIN_PANEL_SDA, INPUT);
      delay(5000);
      pinMode(PIN_LCD_CS, OUTPUT);
      digitalWrite(PIN_LCD_CS, HIGH);
      pinMode(PIN_PANEL_SCK, OUTPUT);
      digitalWrite(PIN_PANEL_SCK, LOW);
      pinMode(PIN_PANEL_SDA, OUTPUT);
      digitalWrite(PIN_PANEL_SDA, LOW);
      Serial.printf("cmd %c: panel lines floated 5 s%s\n", c, c == 'Y' ? " (LCD_CS pulled up)" : "");
      break;
    }
    case '0': case '1': case '2': case '3': case '4': case '5': {
      // 切り分け: LT7680 をやり直してから、パネルのソフトリセットと初期化までの待ち時間を変える
      static const uint32_t WAITS[] = {0, 200, 500, 1000, 2000, 5000};
      uint32_t wait = WAITS[c - '0'];
      bool ok = initLt7680();
      writeReg(0x12, readReg(0x12) | 0x40);
      setupMemory();
      fillRect(0, 0, 479, 479, COLORS[colorIdx]);
      delay(wait);
      resetAndInitPanel();
      Serial.printf("cmd %c: lt7680 %s, waited %lu ms, panel SWRESET + init\n", c, ok ? "OK" : "FAILED", (unsigned long)wait);
      break;
    }
    case 'V':
    case 'X': {
      // 切り分け: XIAO の再起動中と同じく、LT7680 側の線を 1 秒浮かせてから、#0 と同じ手順を行う。
      // V は LCM_RESET (D1) だけ、X は LCM_RESET と LCM_SCS (D0) の両方
      gpio_pullup_dis((gpio_num_t)PIN_RESET);
      pinMode(PIN_RESET, INPUT);
      if (c == 'X') pinMode(PIN_SCS, INPUT);
      delay(1000);
      pinMode(PIN_SCS, OUTPUT);
      digitalWrite(PIN_SCS, HIGH);
      pinMode(PIN_RESET, OUTPUT_OPEN_DRAIN);
      gpio_pullup_en((gpio_num_t)PIN_RESET);
      digitalWrite(PIN_RESET, HIGH);
      bool ok = initLt7680();
      writeReg(0x12, readReg(0x12) | 0x40);
      setupMemory();
      fillRect(0, 0, 479, 479, COLORS[colorIdx]);
      resetAndInitPanel();
      Serial.printf("cmd %c: floated %s 1 s, lt7680 %s, panel SWRESET + init\n", c, c == 'X' ? "D0+D1" : "D1", ok ? "OK" : "FAILED");
      break;
    }
    case 'K': fillRect(0, 0, 479, 479, 0x0000); Serial.println("cmd K: filled black"); break;
    case 'W': fillRect(0, 0, 479, 479, 0xFFFF); Serial.println("cmd W: filled white"); break;
    case 'b': bl = !bl; digitalWrite(PIN_BL, bl); Serial.printf("cmd b: backlight %s\n", bl ? "on" : "off"); break;
    case 'r':
      Serial.printf("cmd r: STSR=0x%02X CCR=0x%02X DPCR=0x%02X 10=0x%02X reset_reason=%d power_on=%s\n",
                    readStatus(), readReg(0x01), readReg(0x12), readReg(0x10), (int)why, powerOn ? "yes" : "no");
      break;
    default: break;
  }
}
