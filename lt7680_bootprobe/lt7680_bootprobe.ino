// lt7680_bootprobe.ino
//
// パネル用の 4 本 (BL_CONTROL=D3, LCD_CS=D2, LCD_DIN=D10, LCD_SCLK=D8) を足したら、
// LT7680 のリセット後に STSR=0x7F (bit1 = 操作禁止) が続くようになった。
// D2 と D3 の High/Low を 4 通り試して、LT7680 をリセットした後の STSR を比べる。

#include <SPI.h>

static const int PIN_SCS    = D0;
static const int PIN_RESET  = D1;
static const int PIN_LCD_CS = D2;
static const int PIN_BL     = D3;
static const int PIN_SCK    = D8;
static const int PIN_MISO   = D9;
static const int PIN_MOSI   = D10;

SPISettings lt(1000000, MSBFIRST, SPI_MODE3);

uint8_t readStatus() {
  SPI.beginTransaction(lt);
  digitalWrite(PIN_SCS, LOW);
  SPI.transfer(0x40);
  uint8_t r = SPI.transfer(0x00);
  digitalWrite(PIN_SCS, HIGH);
  SPI.endTransaction();
  return r;
}

void trial(int lcdCs, int bl) {
  digitalWrite(PIN_LCD_CS, lcdCs);
  digitalWrite(PIN_BL, bl);
  delay(50);
  digitalWrite(PIN_RESET, LOW);
  delay(10);
  digitalWrite(PIN_RESET, HIGH);
  uint32_t t0 = millis();
  int firstNormal = -1;
  uint8_t last = 0;
  while (millis() - t0 < 3000) {
    last = readStatus();
    if (firstNormal < 0 && (last & 0x02) == 0) firstNormal = millis() - t0;
    delay(10);
  }
  Serial.printf("bootprobe: LCD_CS(D2)=%d BL(D3)=%d -> normal after %d ms, STSR at 3s = 0x%02X\n",
                lcdCs, bl, firstNormal, last);
}

void setup() {
  pinMode(PIN_SCS, OUTPUT);
  digitalWrite(PIN_SCS, HIGH);
  pinMode(PIN_LCD_CS, OUTPUT);
  pinMode(PIN_BL, OUTPUT);
  pinMode(PIN_RESET, OUTPUT_OPEN_DRAIN);
  gpio_pullup_en((gpio_num_t)PIN_RESET);
  digitalWrite(PIN_RESET, HIGH);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(1500);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
}

void loop() {
  trial(1, 0);
  trial(0, 0);
  trial(1, 1);
  trial(0, 1);
  digitalWrite(PIN_BL, LOW);
  Serial.println("bootprobe: done");
  delay(3000);
}
