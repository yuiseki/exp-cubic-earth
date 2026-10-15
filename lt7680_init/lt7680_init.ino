// lt7680_init.ino
//
// LT7680A-R の PLL と表示用メモリ (内蔵 SDRAM 128Mb) を初期化し、準備完了のビットを確かめる。
// パネルは使わない。配線は ../WIRING.md の最小構成 (7 系統)。
//
// 手順はデータシート 1.1 節 (PLL)、3 章と 13 章 (REG[E0h]-REG[E4h]) による。
// - 水晶は 10MHz と仮定 (データシートの例と同じ)
// - PLL は 800x480 の例と同じ: PCLK 25MHz、MCLK 50MHz、CCLK 50MHz
//   FOUT = XI * (N / R) / OD。REG[05h] などは OD[7:6] | R[5:1] | N[8] (bit0)、
//   REG[06h] などは N[7:0]
// - SDRAM は LT7680A-R の推奨値: E0h=0x29、E1h=0x03、E3h:E2h=0x061A

#include <SPI.h>

static const int PIN_SCS   = D0;
static const int PIN_RESET = D1;
static const int PIN_SCK   = D8;
static const int PIN_MISO  = D9;
static const int PIN_MOSI  = D10;

SPISettings lt(1000000, MSBFIRST, SPI_MODE3);

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

// 条件が満たされるまで待つ。時間切れなら false
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

bool initLt7680() {
  // ER-PCBA5981-1 の LCM_RESET にはプルアップが無い。内部プルアップで High に保ち、
  // オープンドレインで Low に引く (WIRING.md)
  pinMode(PIN_RESET, OUTPUT_OPEN_DRAIN);
  gpio_pullup_en((gpio_num_t)PIN_RESET);
  digitalWrite(PIN_RESET, LOW);
  delay(10);
  digitalWrite(PIN_RESET, HIGH);
  delay(50);

  if (!waitFor("STSR bit1 = 0 (normal operation)", 1000, [] { return (readStatus() & 0x02) == 0; })) return false;
  Serial.printf("before: STSR=0x%02X CCR=0x%02X\n", readStatus(), readReg(0x01));

  // PLL: XI 10MHz、R=10、OD=4 → FOUT = N MHz / 4
  writeReg(0x05, pllReg(4, 10, 100));  // PCLK = 10 * 100/10 / 4 = 25MHz
  writeReg(0x06, 100 & 0xFF);
  writeReg(0x07, pllReg(4, 10, 200));  // MCLK = 50MHz
  writeReg(0x08, 200 & 0xFF);
  writeReg(0x09, pllReg(4, 10, 200));  // CCLK = 50MHz
  writeReg(0x0A, 200 & 0xFF);
  Serial.printf("PLL regs: 05=0x%02X 06=0x%02X 07=0x%02X 08=0x%02X 09=0x%02X 0A=0x%02X\n",
                readReg(0x05), readReg(0x06), readReg(0x07), readReg(0x08), readReg(0x09), readReg(0x0A));
  writeReg(0x00, 0x80);  // PLL の設定を反映させる
  if (!waitFor("CCR bit7 = 1 (PLL ready)", 1000, [] { return (readReg(0x01) & 0x80) != 0; })) return false;
  // REG[00h] bit7 を書く前の読み返しは古い値を返すことがある。反映後にもう一度読む
  Serial.printf("PLL regs after reconfigure: 05=0x%02X 06=0x%02X 07=0x%02X 08=0x%02X 09=0x%02X 0A=0x%02X SRR=0x%02X\n",
                readReg(0x05), readReg(0x06), readReg(0x07), readReg(0x08), readReg(0x09), readReg(0x0A), readReg(0x00));

  // SDRAM: E0h-E3h は E4h bit2 (SDR_PARAMEN) を立てている間だけ書ける
  writeReg(0xE4, 0x04);
  writeReg(0xE0, 0x29);
  writeReg(0xE1, 0x03);
  writeReg(0xE2, 0x1A);
  writeReg(0xE3, 0x06);
  Serial.printf("SDRAM regs: E0=0x%02X E1=0x%02X E2=0x%02X E3=0x%02X\n",
                readReg(0xE0), readReg(0xE1), readReg(0xE2), readReg(0xE3));
  writeReg(0xE4, 0x05);  // SDR_INITDONE: 0 → 1 で初期化を始める
  if (!waitFor("E4h bit0 = 1 (SDRAM init done)", 1000, [] { return (readReg(0xE4) & 0x01) != 0; })) return false;
  if (!waitFor("STSR bit2 = 1 (display RAM ready)", 1000, [] { return (readStatus() & 0x04) != 0; })) return false;
  return true;
}

void setup() {
  pinMode(PIN_SCS, OUTPUT);
  digitalWrite(PIN_SCS, HIGH);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(1500);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
}

void loop() {
  Serial.println("=== lt7680_init");
  bool ok = initLt7680();
  Serial.printf("result: %s, STSR=0x%02X CCR=0x%02X E4=0x%02X\n", ok ? "INIT OK" : "INIT FAILED",
                readStatus(), readReg(0x01), readReg(0xE4));
  delay(5000);
}
