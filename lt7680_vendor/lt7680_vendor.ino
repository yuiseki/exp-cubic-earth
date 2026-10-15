// lt7680_vendor.ino
//
// lt7680_colorbar を、メーカー (buydisplay) の ER-TFT040-3 用デモコード
// (ER-TFT040-3_ESP32_Tutorial の LCD_init.h, LCD.h, LCD.cpp) の構成にまるごと合わせた版。
// 自前の値では真っ黒だったので、まず動くと分かっている構成で映るかを確かめる。
// 合わせたもの:
// - パネル (ST7701S) の初期化列。LCD_init.h の ST7701S_Initial を機械的に表に変換した
// - 1 語ごとに CS を上げ下げし、CLK を Low → データ → High の順で送る (LCD_init.h と同じ)
// - PLL: OD=3、R=5、N は PCLK 20、MCLK と CCLK 100 (XI 10MHz で PCLK 約 13.3MHz、他は約 66.7MHz)
// - 表示タイミング: HBP/HFP/HSW = 20/20/20、VBP/VFP/VSW = 20/12/3
// - LT7680 のリセット: Low 100ms、その後 200ms 待つ
// - 順番: LT7680 の初期化 → パネルの初期化 → 表示オン
// 配線は WIRING.md の最小構成 + BL=D3, LCD_CS=D2。パネル初期化用の LCD_DIN と LCD_SCLK は、
// デモと同じく LT7680 の SPI と分けて D7 と D6 につなぐ (相乗りでは真っ黒だったため)。

#include <SPI.h>

static const int PIN_SCS    = D0;
static const int PIN_RESET  = D1;
static const int PIN_LCD_CS = D2;
static const int PIN_BL     = D3;
static const int PIN_SCK    = D8;
static const int PIN_MISO   = D9;
static const int PIN_MOSI   = D10;
static const int PIN_PANEL_SCK = D6;  // CON1 19 LCD_SCLK
static const int PIN_PANEL_SDA = D7;  // CON1 18 LCD_DIN

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
  digitalWrite(PIN_BL, HIGH);
  Serial.println("backlight on");
}

void loop() {
  Serial.printf("alive: STSR=0x%02X DPCR=0x%02X\n", readStatus(), readReg(0x12));
  delay(3000);
}
