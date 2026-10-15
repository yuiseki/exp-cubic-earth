// lt7680_backpower.ino
//
// LT7680 に電源が来ているかを、テスター無しで見分ける切り分け用スケッチ。
// XIAO から LT7680 へ出ている線 (SCS, SDI, SCLK, RESET) を全部 High にした場合と
// 全部 Low にした場合で、MISO を内部プルダウンにして読み比べる。
// - 電源が来ていない LT7680 は、High の信号線から保護ダイオード経由で中途半端に給電される。
//   全部 Low にするとその給電が消え、MISO はプルダウンで 0 に落ちるはず
// - 電源が来ていれば、どちらでも同じ値になるはず
// 配線は lt7680_probe と同じ。

static const int PIN_SCS   = D0;
static const int PIN_RESET = D1;
static const int PIN_SCK   = D8;
static const int PIN_MISO  = D9;
static const int PIN_MOSI  = D10;

int readMisoAfter(int level) {
  digitalWrite(PIN_SCS, level);
  digitalWrite(PIN_RESET, level);
  digitalWrite(PIN_SCK, level);
  digitalWrite(PIN_MOSI, level);
  delay(300);
  int ones = 0;
  for (int i = 0; i < 100; i++) { ones += digitalRead(PIN_MISO); delayMicroseconds(100); }
  return ones;
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  pinMode(PIN_SCS, OUTPUT);
  pinMode(PIN_RESET, OUTPUT);
  pinMode(PIN_SCK, OUTPUT);
  pinMode(PIN_MOSI, OUTPUT);
  pinMode(PIN_MISO, INPUT_PULLDOWN);
}

void loop() {
  int hi = readMisoAfter(HIGH);
  int lo = readMisoAfter(LOW);
  Serial.printf("backpower: MISO ones/100 with outputs HIGH=%d, with outputs LOW=%d\n", hi, lo);
  readMisoAfter(HIGH);
  delay(1000);
}
