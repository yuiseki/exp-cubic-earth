// lt7680_vendorflow.ino
//
// メーカー (buydisplay) の ER-TFT040-3 用デモ ER-TFT040-3_ESP32_Tutorial/Display_DMA_Cartoon_Font_test
// の setup() と loop() を、関数の中身まで含めてできるだけそのまま写したもの。
// デモとの違いは次の 3 点だけ。
// - ピンの割り当て (WIRING.md)。パネル初期化線は D2 (CS), D4 (SCLK), D5 (DIN)
// - LT7680 の SPI はデモと同じモード 0 だが、速さは 20MHz ではなく 1MHz (ブレッドボードでの実績に合わせる)
// - BL_CONTROL はデモでは 3.3V に直結。ここでは D3 を起動直後から High にする
//
// 2026-10-15、自前の初期化手順は電源投入でも映ったり映らなかったりした。
// メーカーが実機で確かめている手順に寄せて、電源投入で映るかを見る。

#include <SPI.h>

static const int PIN_SCS    = D0;
static const int PIN_RESET  = D1;
static const int PIN_LCD_CS = D2;
static const int PIN_BL     = D3;
static const int PIN_PANEL_SCK = D4;  // CON1 19 LCD_SCLK
static const int PIN_PANEL_SDA = D5;  // CON1 18 LCD_DIN
static const int PIN_SCK    = D8;
static const int PIN_MISO   = D9;
static const int PIN_MOSI   = D10;

SPISettings lt(1000000, MSBFIRST, SPI_MODE0);

// ---- LT7680 (LCD.cpp の SPI_CmdWrite / SPI_DataWrite / SPI_StatusRead / SPI_DataRead と同じ) ----

uint8_t xfer16(uint8_t prefix, uint8_t data) {
  SPI.beginTransaction(lt);
  digitalWrite(PIN_SCS, LOW);
  SPI.transfer(prefix);
  uint8_t r = SPI.transfer(data);
  digitalWrite(PIN_SCS, HIGH);
  SPI.endTransaction();
  return r;
}
void cmdWrite(uint8_t c) { xfer16(0x00, c); }
void dataWrite(uint8_t d) { xfer16(0x80, d); }
uint8_t dataRead() { return xfer16(0xC0, 0x00); }
uint8_t statusRead() { return xfer16(0x40, 0x00); }
void regWrite(uint8_t r, uint8_t v) { cmdWrite(r); dataWrite(v); }
uint8_t regRead(uint8_t r) { cmdWrite(r); return dataRead(); }
void regAnd(uint8_t r, uint8_t m) { cmdWrite(r); uint8_t t = dataRead(); dataWrite(t & m); }
void regOr(uint8_t r, uint8_t m) { cmdWrite(r); uint8_t t = dataRead(); dataWrite(t | m); }

// LCD.cpp の HW_Reset
void hwReset() {
  // LCM_RESET は基板にプルアップが無い。デモは出力で駆動するが、LT7680 もこのピンにリセットを出す
  // (オープンコレクタ) ので、オープンドレインと内部プルアップで同じ波形を作る
  digitalWrite(PIN_RESET, LOW);
  delay(100);
  digitalWrite(PIN_RESET, HIGH);
  delay(200);
}

// LCD.cpp の System_Check_Temp
void systemCheckTemp() {
  uint8_t i = 0;
  bool ok = false;
  do {
    uint8_t j = statusRead();
    if ((j & 0x02) == 0x00) {
      delay(2);
      cmdWrite(0x01);
      delay(2);
      uint8_t temp = dataRead();
      if ((temp & 0x80) == 0x80) {
        ok = true;
        i = 0;
      } else {
        delay(2);
        cmdWrite(0x01);
        delay(2);
        dataWrite(0x80);
      }
    } else {
      ok = false;
      i++;
    }
    if (!ok && i == 5) {  // デモと同じく、5 回続けて操作禁止なら LT7680 をリセットし直す
      ok = false;
      hwReset();
      i = 0;
    }
  } while (!ok);
}

// LCD.cpp の PLL_Initial (OD のビット値 2 = 3 分周、R=5。N は PCLK 20、MCLK と CCLK 100)
void pllInitial() {
  regWrite(0x05, (2 << 6) | (5 << 1) | ((20 >> 8) & 1));
  regWrite(0x07, (2 << 6) | (5 << 1) | ((100 >> 8) & 1));
  regWrite(0x09, (2 << 6) | (5 << 1) | ((100 >> 8) & 1));
  regWrite(0x06, 20);
  regWrite(0x08, 100);
  regWrite(0x0A, 100);
  cmdWrite(0x00);
  delayMicroseconds(1);
  dataWrite(0x80);
  delay(1);
}

// LCD.cpp の SDRAM_initail
void sdramInitial() {
  uint16_t itv = (64000000 / 8192) / (1000 / 60);
  itv -= 2;
  regWrite(0xE0, 0x29);
  regWrite(0xE1, 0x03);
  regWrite(0xE2, itv & 0xFF);
  regWrite(0xE3, itv >> 8);
  regWrite(0xE4, 0x01);
  while ((statusRead() & 0x04) == 0x00) {
  }
  delay(1);
}

// LCD.h の表示パラメータ
static const uint16_t XSIZE = 480, YSIZE = 480;
static const uint16_t VBPD = 20, VFPD = 12, VSPW = 3, HBPD = 20, HFPD = 20, HSPW = 20;

// LCD.cpp の initial() と、そこから呼ばれる関数
void initial() {
  pllInitial();
  sdramInitial();
  regAnd(0x01, 0xEF); regOr(0x01, 0x08);  // TFT_18bit
  regOr(0x01, 0x01);                      // Host_Bus_16bit
  regAnd(0x02, 0x7F); regOr(0x02, 0x40);  // RGB_16b_16bpp
  regAnd(0x02, 0xFB); regAnd(0x02, 0xFD); // MemWrite_Left_Right_Top_Down
  regAnd(0x03, 0xFB);                     // Graphic_Mode
  regAnd(0x03, 0xFD); regAnd(0x03, 0xFE); // Memory_Select_SDRAM
  regAnd(0x12, 0xEF);                     // HSCAN_L_to_R
  regAnd(0x12, 0xF7);                     // VSCAN_T_to_B
  regAnd(0x12, 0xF8);                     // PDATA_Set_RGB
  regAnd(0x12, 0x7F);                     // PCLK: 立ち上がり
  regAnd(0x13, 0x7F);                     // HSYNC: Low アクティブ
  regAnd(0x13, 0xBF);                     // VSYNC: Low アクティブ
  regAnd(0x13, 0xDF);                     // DE: High アクティブ
  // LCD_HorizontalWidth_VerticalHeight
  regWrite(0x14, XSIZE / 8 - 1);
  regWrite(0x15, XSIZE % 8);
  regWrite(0x1A, (YSIZE - 1) & 0xFF);
  regWrite(0x1B, (YSIZE - 1) >> 8);
  // LCD_Horizontal_Non_Display, HSYNC_Start_Position, HSYNC_Pulse_Width
  regWrite(0x16, HBPD / 8 - 1);
  regWrite(0x17, HBPD % 8);
  regWrite(0x18, HFPD / 8 - 1);
  regWrite(0x19, HSPW / 8 - 1);
  // LCD_Vertical_Non_Display, VSYNC_Start_Position, VSYNC_Pulse_Width
  regWrite(0x1C, (VBPD - 1) & 0xFF);
  regWrite(0x1D, (VBPD - 1) >> 8);
  regWrite(0x1E, VFPD - 1);
  regWrite(0x1F, VSPW - 1);
  regAnd(0x10, 0xF7); regOr(0x10, 0x04);  // Select_Main_Window_16bpp
  regAnd(0x5E, 0xFB);                     // Memory_XY_Mode
  regAnd(0x5E, 0xFD); regOr(0x5E, 0x01);  // Memory_16bpp_Mode
  regAnd(0x10, 0xF7); regOr(0x10, 0x04);  // Select_Main_Window_16bpp
}

// ---- ST7701S (LCD_init.h の SPI_WriteComm / SPI_WriteData / ST7701S_Initial と同じ) ----

void swSpiSend(uint8_t v) {
  for (int n = 0; n < 8; n++) {
    digitalWrite(PIN_PANEL_SCK, LOW);
    digitalWrite(PIN_PANEL_SDA, (v & 0x80) ? HIGH : LOW);
    digitalWrite(PIN_PANEL_SCK, HIGH);
    v <<= 1;
  }
}
void spiWriteComm(uint8_t c) {
  digitalWrite(PIN_LCD_CS, LOW);
  digitalWrite(PIN_PANEL_SDA, LOW);
  digitalWrite(PIN_PANEL_SCK, LOW);
  digitalWrite(PIN_PANEL_SCK, HIGH);
  swSpiSend(c);
  digitalWrite(PIN_LCD_CS, HIGH);
}
void spiWriteData(uint8_t d) {
  digitalWrite(PIN_LCD_CS, LOW);
  digitalWrite(PIN_PANEL_SDA, HIGH);
  digitalWrite(PIN_PANEL_SCK, LOW);
  digitalWrite(PIN_PANEL_SCK, HIGH);
  swSpiSend(d);
  digitalWrite(PIN_LCD_CS, HIGH);
}

// LCD_init.h の ST7701S_Initial を機械的に表にしたもの。
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
  0x00, 0xFE, 20,
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
  0x00, 0xFE, 120,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x13,
  0xE8, 2, 0x00, 0x0C,
  0x00, 0xFE, 10,
  0xE8, 2, 0x00, 0x00,
  0xFF, 5, 0x77, 0x01, 0x00, 0x00, 0x00,
  0x36, 1, 0x00,
  0x3A, 1, 0x66,
  0x21, 0,
  0x29, 0,
  0x00, 0xFE, 20,
};

void st7701sInitial() {
  pinMode(PIN_LCD_CS, OUTPUT);
  digitalWrite(PIN_LCD_CS, HIGH);
  pinMode(PIN_PANEL_SCK, OUTPUT);
  digitalWrite(PIN_PANEL_SCK, LOW);
  pinMode(PIN_PANEL_SDA, OUTPUT);
  digitalWrite(PIN_PANEL_SDA, LOW);
  size_t i = 0;
  while (i < sizeof(ST7701S_ER_TFT040_3)) {
    uint8_t cmd = ST7701S_ER_TFT040_3[i++];
    uint8_t n = ST7701S_ER_TFT040_3[i++];
    if (n == 0xFE) {
      delay(ST7701S_ER_TFT040_3[i++]);
      continue;
    }
    spiWriteComm(cmd);
    for (uint8_t k = 0; k < n; k++) spiWriteData(ST7701S_ER_TFT040_3[i++]);
  }
}

// LCD.cpp の Display_ON
void displayOn() { regOr(0x12, 0x40); }

// ---- loop() で使う描画 (LCD.cpp と同じ) ----

void reg16(uint8_t r, uint16_t v) { regWrite(r, v & 0xFF); regWrite(r + 1, v >> 8); }

void drawSquareFill(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t color) {
  regWrite(0xD2, color >> 8);  // Foreground_color_65k
  regWrite(0xD3, color >> 3);
  regWrite(0xD4, color << 3);
  reg16(0x68, x1);  // Square_Start_XY
  reg16(0x6A, y1);
  reg16(0x6C, x2);  // Square_End_XY
  reg16(0x6E, y2);
  regWrite(0x76, 0xE0);  // Start_Square_Fill
  while (statusRead() & 0x08) {
  }
}

void setup() {
  // ピンを先に決まった状態にする (デモにはない。XIAO の起動中に浮いていた線を早く固定する)
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
  pinMode(PIN_BL, OUTPUT);
  digitalWrite(PIN_BL, HIGH);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);

  // ここからデモの setup() と同じ
  delay(100);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);  // Parallel_Init
  hwReset();
  systemCheckTemp();
  delay(100);
  while (statusRead() & 0x02) {
  }
  initial();
  st7701sInitial();
  displayOn();
  Serial.println("vendorflow: setup done");
}

void loop() {
  // デモの loop() の冒頭と同じ
  regAnd(0x10, 0xF7); regOr(0x10, 0x04);  // Select_Main_Window_16bpp
  for (int i = 0; i < 4; i++) regWrite(0x20 + i, 0);  // Main_Image_Start_Address(0)
  reg16(0x24, XSIZE);                     // Main_Image_Width
  reg16(0x26, 0); reg16(0x28, 0);         // Main_Window_Start_XY(0,0)
  for (int i = 0; i < 4; i++) regWrite(0x50 + i, 0);  // Canvas_Image_Start_address(0)
  reg16(0x54, XSIZE);                     // Canvas_image_width
  reg16(0x56, 0); reg16(0x58, 0);         // Active_Window_XY(0,0)
  reg16(0x5A, XSIZE); reg16(0x5C, YSIZE); // Active_Window_WH

  const uint16_t colors[] = {0xF800, 0x07E0, 0x001F, 0x07FF, 0xFFE0, 0xF81F, 0x0000};
  for (uint16_t c : colors) {
    drawSquareFill(0, 0, XSIZE, YSIZE, c);
    delay(1000);
  }
}
