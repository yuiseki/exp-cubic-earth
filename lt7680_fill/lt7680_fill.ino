// lt7680_fill.ino
//
// lt7680_vendor (カラーバーが映った構成) から、カラーバーを切り、表示用メモリを
// LT7680 の図形描画で単色に塗りつぶして映す。画素の転送はまだ使わない。
// 表示用メモリの設定と描画の手順は、メーカーのデモ (ER-TFT040-3_ESP32_Tutorial の
// Display_DMA_Cartoon_Font_test.ino の loop() と LCD.cpp) と同じ。
// 配線は WIRING.md (パネル初期化線は D6/D7 に分ける)。

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

// ---- 表示タイミング (480x480) ----
static const int HBP = 20, HFP = 20, HPW = 20;  // LCD.h の LCD_HBPD/HFPD/HSPW
static const int VBP = 20, VFP = 12, VPW = 3;   // LCD.h の LCD_VBPD/VFPD/VSPW

bool initLt7680() {
  digitalWrite(PIN_RESET, LOW);  // LCD.cpp の HW_Reset と同じ長さ
  delay(100);
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
  Serial.printf("fill 0x%04X took %lu us\n", color, (unsigned long)(micros() - t0));
}

void setup() {
  // LCM_RESET は基板にプルアップが無く、浮くとノイズで LT7680 がリセットを繰り返す。
  // 起動の最初に High に固定する
  pinMode(PIN_RESET, OUTPUT_OPEN_DRAIN);
  gpio_pullup_en((gpio_num_t)PIN_RESET);
  digitalWrite(PIN_RESET, HIGH);
  pinMode(PIN_SCS, OUTPUT);
  digitalWrite(PIN_SCS, HIGH);
  pinMode(PIN_LCD_CS, OUTPUT);
  digitalWrite(PIN_LCD_CS, HIGH);
  pinMode(PIN_BL, OUTPUT);
  digitalWrite(PIN_BL, LOW);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(1500);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);

  bool ok = initLt7680();
  Serial.printf("lt7680: %s\n", ok ? "INIT OK" : "INIT FAILED");
  initPanel();
  writeReg(0x12, readReg(0x12) | 0x40);  // 表示オン
  setupMemory();
  fillRect(0, 0, 479, 479, 0x0000);
  digitalWrite(PIN_BL, HIGH);
  Serial.println("backlight on");
}

void loop() {
  const struct { uint16_t c; const char *name; } colors[] = {
    {0xF800, "red"}, {0x07E0, "green"}, {0x001F, "blue"}, {0xFFFF, "white"}, {0x0000, "black"},
  };
  for (auto &k : colors) {
    Serial.printf("color: %s\n", k.name);
    fillRect(0, 0, 479, 479, k.c);
    delay(1500);
  }
}
