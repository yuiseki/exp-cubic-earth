// lt7680_colorbar.ino
//
// LT7680A-R の内蔵カラーバーを、ST7701S 系の 4 インチ 480x480 パネルに出す最初の表示試験。
// 画像は送らない。LT7680 → パネルの RGB の経路と、パネルの最小限の初期化を確かめる。
//
// 配線: ../WIRING.md の最小構成 7 系統に、次の 4 本を足す
//   CON1 9  BL_CONTROL = D3
//   CON1 16 LCD_CS     = D2
//   CON1 18 LCD_DIN    = D10 (LCM_SDI と同じピン)
//   CON1 19 LCD_SCLK   = D8  (LCM_SCLK と同じピン)
//
// パネルの初期化列はメーカーの資料が手に入っていないので、ST7701S の標準コマンドだけを送る
// (ソフトリセット、スリープ解除、色形式、表示オン)。色味やガンマは正しくない前提。
// 表示タイミングも、480x480 の ST7701S でよく使われる程度の値から始める。

#include <SPI.h>

static const int PIN_SCS    = D0;
static const int PIN_RESET  = D1;
static const int PIN_LCD_CS = D2;
static const int PIN_BL     = D3;
static const int PIN_SCK    = D8;
static const int PIN_MISO   = D9;
static const int PIN_MOSI   = D10;

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

uint8_t pllReg(uint8_t od, uint8_t r, uint16_t n) {
  uint8_t odBits = (od == 1) ? 0 : (od == 2) ? 1 : (od == 3) ? 2 : 3;
  return (odBits << 6) | ((r & 0x1F) << 1) | ((n >> 8) & 1);
}

// ---- ST7701S (3 線 SPI、9 ビット: 先頭 1 ビットが 0=コマンド / 1=データ) ----
// SCK と MOSI は LT7680 と共有しているので、送る間だけ SPI から外して手で信号を作る

void panelBit(int b) {
  digitalWrite(PIN_MOSI, b);
  delayMicroseconds(2);
  digitalWrite(PIN_SCK, HIGH);  // 立ち上がりで取り込まれる
  delayMicroseconds(2);
  digitalWrite(PIN_SCK, LOW);
}

void panel9(int dc, uint8_t v) {
  panelBit(dc);
  for (int i = 7; i >= 0; i--) panelBit((v >> i) & 1);
}

void panelCmd(uint8_t cmd, const uint8_t *data = nullptr, size_t n = 0) {
  digitalWrite(PIN_LCD_CS, LOW);
  delayMicroseconds(2);
  panel9(0, cmd);
  for (size_t i = 0; i < n; i++) panel9(1, data[i]);
  delayMicroseconds(2);
  digitalWrite(PIN_LCD_CS, HIGH);
  delayMicroseconds(5);
}

// ST7701S の初期化列。メーカーの資料が無いので、同じ 4 インチ 480x480 の ST7701S を使う
// ESP32-4848S040 向けとして Arduino_GFX (moononournation/Arduino_GFX、
// src/display/Arduino_RGB_Display.h の st7701_type1_init_operations) に載っている値を借りた。
// このパネル (FPC の印字 HD40010C40) で正しい値かは確かめていない。
// 書式: コマンド, データ長, データ...。データ長 0xFF は「待ち時間 (ms) を次の 1 バイトで指定」
static const uint8_t ST7701S_TYPE1[] = {
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x10,  // Command2 BK0
  0xC0, 2, 0x3B, 0x00,                    // 表示行数 (0x3B + 1) * 8 = 480
  0xC1, 2, 0x0D, 0x02,                    // VBP / VFP
  0xC2, 2, 0x31, 0x05,
  0xCD, 1, 0x08,
  0xB0, 16, 0x00, 0x11, 0x18, 0x0E, 0x11, 0x06, 0x07, 0x08, 0x07, 0x22, 0x04, 0x12, 0x0F, 0xAA, 0x31, 0x18,  // 正のガンマ
  0xB1, 16, 0x00, 0x11, 0x19, 0x0E, 0x12, 0x07, 0x08, 0x08, 0x08, 0x22, 0x04, 0x11, 0x11, 0xA9, 0x32, 0x18,  // 負のガンマ
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x11,  // Command2 BK1 (電源)
  0xB0, 1, 0x60,
  0xB1, 1, 0x32,
  0xB2, 1, 0x07,
  0xB3, 1, 0x80,
  0xB5, 1, 0x49,
  0xB7, 1, 0x85,
  0xB8, 1, 0x21,
  0xC1, 1, 0x78,
  0xC2, 1, 0x78,
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
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x13,  // Command2 BK3
  0xE5, 1, 0xE4,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x00,  // Command2 を抜ける
  0x21, 0,                                // 反転 (IPS)
  0x3A, 1, 0x60,                          // RGB666
  0x11, 0xFF, 120,                        // スリープ解除
  0x29, 0,                                // 表示オン
};

void sendPanelInit() {
  size_t i = 0;
  while (i < sizeof(ST7701S_TYPE1)) {
    uint8_t cmd = ST7701S_TYPE1[i++];
    uint8_t n = ST7701S_TYPE1[i++];
    if (n == 0xFF) {
      panelCmd(cmd);
      delay(ST7701S_TYPE1[i++]);
    } else {
      panelCmd(cmd, &ST7701S_TYPE1[i], n);
      i += n;
    }
  }
}

// パネルから 1 バイト読む (3 線 SPI)。コマンドの 9 ビットを送った後、SDA を入力にして
// 立ち上がりで読む。先頭に 1 ビットのダミーがあるかが分からないので、9 ビット読んで両方の解釈を出す
uint16_t panelRead9(uint8_t cmd) {
  digitalWrite(PIN_LCD_CS, LOW);
  delayMicroseconds(2);
  panel9(0, cmd);
  pinMode(PIN_MOSI, INPUT);
  uint16_t v = 0;
  for (int i = 0; i < 9; i++) {
    delayMicroseconds(2);
    digitalWrite(PIN_SCK, HIGH);
    delayMicroseconds(2);
    v = (v << 1) | digitalRead(PIN_MOSI);
    digitalWrite(PIN_SCK, LOW);
  }
  digitalWrite(PIN_LCD_CS, HIGH);
  pinMode(PIN_MOSI, OUTPUT);
  digitalWrite(PIN_MOSI, LOW);
  delayMicroseconds(5);
  return v;
}

void dumpPanel(const char *when) {
  const uint8_t cmds[] = {0x0A, 0x0B, 0x0C, 0x0D, 0xDA, 0xDB, 0xDC};
  for (uint8_t c : cmds) {
    uint16_t v = panelRead9(c);
    Serial.printf("panel read %s: cmd 0x%02X -> 9 bits 0x%03X (no dummy 0x%02X, with dummy 0x%02X)\n",
                  when, c, v, (v >> 1) & 0xFF, v & 0xFF);
  }
}

void initPanel() {
  SPI.end();
  pinMode(PIN_SCK, OUTPUT);
  pinMode(PIN_MOSI, OUTPUT);
  digitalWrite(PIN_SCK, LOW);
  digitalWrite(PIN_MOSI, LOW);

  dumpPanel("before");
  panelCmd(0x01);  // SWRESET
  delay(150);
  sendPanelInit();
  Serial.println("panel: SWRESET + ST7701S type1 init sent");
  dumpPanel("after");

  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
}

// ---- 表示タイミング (480x480) ----
static const int HBP = 40, HFP = 16, HPW = 8;  // HBP と HFP、HPW は 8 の倍数で設定する
static const int VBP = 16, VFP = 10, VPW = 4;

bool initLt7680() {
  digitalWrite(PIN_RESET, LOW);
  delay(10);
  digitalWrite(PIN_RESET, HIGH);
  delay(50);
  if (!waitFor("normal operation", 1000, [] { return (readStatus() & 0x02) == 0; })) return false;

  // PLL: XI 10MHz 仮定、R=10、OD=4。PCLK 20MHz、MCLK と CCLK 50MHz
  writeReg(0x05, pllReg(4, 10, 80));
  writeReg(0x06, 80);
  writeReg(0x07, pllReg(4, 10, 200));
  writeReg(0x08, 200);
  writeReg(0x09, pllReg(4, 10, 200));
  writeReg(0x0A, 200);
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
  writeReg(0x17, 0);
  writeReg(0x18, HFP / 8 - 1);
  writeReg(0x19, HPW / 8 - 1);
  writeReg(0x1A, (480 - 1) & 0xFF);
  writeReg(0x1B, (480 - 1) >> 8);
  writeReg(0x1C, (VBP - 1) & 0xFF);
  writeReg(0x1D, (VBP - 1) >> 8);
  writeReg(0x1E, VFP - 1);
  writeReg(0x1F, VPW - 1);
  writeReg(0x12, 0x60);  // 表示オン + カラーバー、PCLK の立ち上がりで取り込み、RGB の順
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
  digitalWrite(PIN_BL, HIGH);
  Serial.println("backlight on");
}

void loop() {
  Serial.printf("alive: STSR=0x%02X DPCR=0x%02X\n", readStatus(), readReg(0x12));
  delay(3000);
}
