// lt7680_probe.ino
//
// XIAO ESP32-S3 から ER-PCBA5981-1 (LT7680A-R) の SPI が通っているかを確かめる最小ファーム。
// 表示はしない。状態レジスタを読み、書き読みできるレジスタに値を書いて読み返すだけ。
//
// 配線 (2026-10-15):
//   CON1 5 LCM_SCS  = D0
//   CON1 6 LCM_SDO  = D9  (MISO)
//   CON1 7 LCM_SDI  = D10 (MOSI)  パネル初期化用 LCD_DIN (18) と共有
//   CON1 8 LCM_SCLK = D8  (SCK)   パネル初期化用 LCD_SCLK (19) と共有
//   CON1 9 BL_CONTROL = D3
//   CON1 11 LCM_RESET = D1
//   CON1 16 LCD_CS  = D2
//   CON1 3,4 VDD = 5V / 1,2 GND
//
// XIAO ESP32-S3 Sense では D9 (MISO) が、XIAO の出力を全部 Low にしても内部プルダウンでも
// High のままだった (2026-10-15)。Sense の拡張ボードの microSD が D8/D9/D10 を共有しているので、
// そのプルアップと考えると説明できる (回路図では未確認)。この用途には Sense でない XIAO を使う。
// 何もつながっていないとき、Sense でない XIAO の MISO はプルアップ/プルダウンにそのまま従う。
//
// LT7680 の SPI (データシート 2.1 節、図 2-4, 2-5):
//   モード 3。1 回の転送は 16 クロックで、先頭 8 ビットが前置き (bit7=A0, bit6=RW#)、
//   続く 8 ビットがデータ。
//     0x00 + reg  : レジスタ番号を書く
//     0x80 + data : 選んだレジスタにデータを書く
//     0x40 → 読む : 状態レジスタ (STSR) を読む
//     0xC0 → 読む : 選んだレジスタを読む

#include <SPI.h>

static const int PIN_SCS    = D0;
static const int PIN_RESET  = D1;
static const int PIN_LCD_CS = D2;
static const int PIN_BL     = D3;
static const int PIN_SCK    = D8;
static const int PIN_MISO   = D9;
static const int PIN_MOSI   = D10;

static const uint32_t SPI_HZ = 1000000;  // まず遅く。上限は 50MHz

SPISettings lt(SPI_HZ, MSBFIRST, SPI_MODE3);

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

uint8_t readStatus() {
  return xfer16(0x40, 0x00);
}

void setup() {
  // 共有している SCK/MOSI のデータを関係ない側が受け取らないよう、CS を真っ先に上げる
  pinMode(PIN_SCS, OUTPUT);
  digitalWrite(PIN_SCS, HIGH);
  pinMode(PIN_LCD_CS, OUTPUT);
  digitalWrite(PIN_LCD_CS, HIGH);
  pinMode(PIN_BL, OUTPUT);
  digitalWrite(PIN_BL, LOW);

  // LCM_RESET は LT7680 自身もリセットを出すオープンコレクタの双方向ピン。
  // High を押し付けず、Low に引くか手を離すかだけにする
  pinMode(PIN_RESET, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_RESET, HIGH);
  // ER-PCBA5981-1 の LCM_RESET にはプルアップが無い。手を離すと線が浮き、
  // 1 秒の 7 割以上が Low と読めるほどノイズを拾った (2026-10-15)。内部プルアップで High に保つ
  gpio_pullup_en((gpio_num_t)PIN_RESET);

  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(1500);

  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
  // 切り分け: MISO を内部プルダウンにする。誰も駆動していなければ 0x00 と読める
  gpio_pulldown_en((gpio_num_t)PIN_MISO);
  gpio_pullup_dis((gpio_num_t)PIN_MISO);

  digitalWrite(PIN_RESET, LOW);
  delay(10);
  digitalWrite(PIN_RESET, HIGH);
  delay(200);
  Serial.printf("lt7680_probe: reset released, RESET pin reads %d\n", digitalRead(PIN_RESET));
}

// 切り分け: SPI モードとクロックを全組み合わせで振り、読み返しが通るものを探す
void sweepModes() {
  const uint8_t modes[4] = {SPI_MODE0, SPI_MODE1, SPI_MODE2, SPI_MODE3};
  const uint32_t hzs[2] = {100000, 1000000};
  for (int h = 0; h < 2; h++) {
    for (int m = 0; m < 4; m++) {
      lt = SPISettings(hzs[h], MSBFIRST, modes[m]);
      uint8_t st = readStatus();
      writeReg(0x20, 0x54);
      uint8_t a = readReg(0x20);
      writeReg(0x20, 0xA8);
      uint8_t b = readReg(0x20);
      writeReg(0x20, 0x00);
      Serial.printf("sweep mode%d %7luHz: STSR=0x%02X read 0x%02X/0x%02X %s\n", m, (unsigned long)hzs[h], st, a, b,
                    (a == 0x54 && b == 0xA8) ? "OK" : "NG");
    }
  }
  lt = SPISettings(SPI_HZ, MSBFIRST, SPI_MODE3);
}

// JP1 の 6 番 (基板のレギュレーターが出す 3.3V) を D5 に引き込んで ADC で読む。
// ADC の上限は約 3.1V なので、3.3V が来ていれば上限付近に張り付く
static const int PIN_V33 = D5;

void loop() {
  // 浮いた線は ADC で何でも読めてしまう。プルダウンとプルアップの両方で読み、
  // どちらでも同じ値なら本当にその電圧につながっている。食い違えば浮いている
  uint32_t mvDown = 0, mvUp = 0;
  gpio_pullup_dis((gpio_num_t)PIN_V33); gpio_pulldown_en((gpio_num_t)PIN_V33); delay(5);
  for (int i = 0; i < 16; i++) mvDown += analogReadMilliVolts(PIN_V33);
  gpio_pulldown_dis((gpio_num_t)PIN_V33); gpio_pullup_en((gpio_num_t)PIN_V33); delay(5);
  for (int i = 0; i < 16; i++) mvUp += analogReadMilliVolts(PIN_V33);
  gpio_pullup_dis((gpio_num_t)PIN_V33); gpio_pulldown_en((gpio_num_t)PIN_V33);
  Serial.printf("D5: pulldown %lu mV, pullup %lu mV\n", (unsigned long)(mvDown / 16), (unsigned long)(mvUp / 16));
  sweepModes();
  // 切り分け: LCM_RESET を 1 秒間、約 1 マイクロ秒おきに読み、Low の回数と最長の連続を数える。
  // LT7680 が内部リセットを繰り返していれば Low が周期的に出る
  uint32_t lows = 0, samples = 0, run = 0, longest = 0, edges = 0;
  int prev = 1;
  uint32_t t0 = micros();
  while (micros() - t0 < 1000000) {
    int v = digitalRead(PIN_RESET);
    samples++;
    if (v == 0) { lows++; run++; if (run > longest) longest = run; } else { run = 0; }
    if (v != prev) edges++;
    prev = v;
  }
  gpio_pullup_en((gpio_num_t)PIN_MISO); gpio_pulldown_dis((gpio_num_t)PIN_MISO); delayMicroseconds(50);
  int misoUp = digitalRead(PIN_MISO);
  gpio_pulldown_en((gpio_num_t)PIN_MISO); gpio_pullup_dis((gpio_num_t)PIN_MISO); delayMicroseconds(50);
  int misoDown = digitalRead(PIN_MISO);
  Serial.printf("RESET: %u/%u samples low, longest low run %u samples, %u edges | MISO pullup=%d pulldown=%d\n",
                lows, samples, longest, edges, misoUp, misoDown);
  uint8_t st = readStatus();
  Serial.printf("STSR=0x%02X (wfifo_full=%d wfifo_empty=%d rfifo_full=%d rfifo_empty=%d busy=%d sdram_ready=%d inhibit=%d)\n",
                st, (st >> 7) & 1, (st >> 6) & 1, (st >> 5) & 1, (st >> 4) & 1,
                (st >> 3) & 1, (st >> 2) & 1, (st >> 1) & 1);

  // REG[20h] は MISA[7:0]。読み書きでき、bit[1:0] は 0 でなければならない
  uint8_t before = readReg(0x20);
  writeReg(0x20, 0x54);
  uint8_t a = readReg(0x20);
  writeReg(0x20, 0xA8);
  uint8_t b = readReg(0x20);
  writeReg(0x20, before);
  Serial.printf("REG20 before=0x%02X wrote 0x54 read 0x%02X, wrote 0xA8 read 0x%02X -> %s\n",
                before, a, b, (a == 0x54 && b == 0xA8) ? "READBACK OK" : "READBACK NG");
  delay(2000);
}
