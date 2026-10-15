// netfinder.ino
//
// D5 にクリップした網 (ER-PCBA5981-1 の JP1 1 番 = 基板の GND) が、XIAO のどのピンと
// つながっているかを探す切り分け用スケッチ。
// 全ピンを入力 (駆動しない) にした状態で D5 を読み、次に 1 本ずつ 50ms だけ High にして読む。
// 基板には電源を入れない前提。駆動はごく短く、電流は GPIO が出せる範囲に限られる。

static const int PIN_PROBE = D5;
static const int CANDIDATES[] = {D0, D1, D2, D3, D4, D6, D7, D8, D9, D10};
static const char *NAMES[] = {"D0", "D1", "D2", "D3", "D4", "D6", "D7", "D8", "D9", "D10"};
static const int N = sizeof(CANDIDATES) / sizeof(CANDIDATES[0]);

uint32_t probeMv() {
  uint32_t mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(PIN_PROBE);
  return mv / 8;
}

void allInputs() {
  for (int i = 0; i < N; i++) pinMode(CANDIDATES[i], INPUT);
}

void setup() {
  allInputs();
  pinMode(PIN_PROBE, INPUT_PULLDOWN);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(1500);
}

void loop() {
  allInputs();
  delay(20);
  Serial.printf("netfinder: all inputs -> D5 %lu mV\n", (unsigned long)probeMv());
  for (int i = 0; i < N; i++) {
    allInputs();
    pinMode(CANDIDATES[i], OUTPUT);
    digitalWrite(CANDIDATES[i], HIGH);
    delay(50);
    uint32_t mv = probeMv();
    pinMode(CANDIDATES[i], INPUT);
    Serial.printf("netfinder: %s HIGH -> D5 %lu mV\n", NAMES[i], (unsigned long)mv);
  }
  // 直結と回り込みを分ける: 全部 High にしておき、1 本ずつ Low にする。
  // 網を 0V 近くまで引き下げられるのは、その網に直接つながっているピンだけ
  for (int i = 0; i < N; i++) {
    for (int k = 0; k < N; k++) { pinMode(CANDIDATES[k], OUTPUT); digitalWrite(CANDIDATES[k], HIGH); }
    digitalWrite(CANDIDATES[i], LOW);
    delay(50);
    uint32_t mv = probeMv();
    Serial.printf("netfinder: all HIGH but %s LOW -> D5 %lu mV\n", NAMES[i], (unsigned long)mv);
  }
  Serial.println("netfinder: done");
  allInputs();
  delay(3000);
}
