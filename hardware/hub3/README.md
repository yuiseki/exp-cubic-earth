# hub3

XIAO ESP32-S3 (ピンソケットで挿す)、74HC138、20 ピン 1.0mm の FFC コネクタ 3 個を載せた 42 x 42 mm の 2 層基板。ER-PCBA5981-1 を 3 枚つなぎ、`lt7680_multi` の構成 3 (`-DNUM_BOARDS=3`) と同じ配線にする (`WIRING.md`)。

- J1 (LCD0、左の辺)、J2 (LCD1、上の辺)、J3 (LCD2、右の辺): BOOMELE 1.0-20P 下接 (LCSC C2998680)。口は基板の外を向く。3 個は基板の中心のまわりに 90 度ずつ回した同じ置き方
- U2: XIAO ESP32-S3。USB-C は下の辺 (FFC の無い辺) に向く
- U1: 74HC138 (SOIC-16、LCSC C2674688)。A, B, C = D0, D2, D6。基板 b の LCM_SCS は Yb、LCD_CS は Y(3+b)、Y6 と Y7 は空き
- C1 100nF (74HC138 の 3.3V)、C2 10uF (5V)
- 角に M2 の穴 4 個

## 作り方

すべてスクリプトから作る。回路図と基板を手で直したら、次に `make.py` を流すと上書きされる。

```sh
/usr/bin/python3 make.py    # 回路図、部品を置いた基板、ライブラリ (KiCad 10 の pcbnew モジュールを使う)
/usr/bin/python3 route.py   # Freerouting で配線し、GND のベタを塗る
./check.sh                  # ERC、DRC (回路図との突き合わせ込み)、test_hub3.py。どれも 0 件で通る
```

- 部品と網の表は `make.py` の先頭にあり、回路図と基板の両方がそこから作られる
- `test_hub3.py` は `make.py` とは別に、`WIRING.md` の配線表から各パッドの網を確かめる
- Freerouting は Linux 向けの実行環境同梱版 (`freerouting-2.4.1-linux-x64.zip`) を `~/.local/share/freerouting/2.4.1/` に置いて使う。jar 単体は Java 25 が要る
- 配線するときは GND のベタを外し、GND も線で引いてからベタを戻す。ベタを残したまま渡すと、Freerouting は GND を引かず、表のベタが島に分かれる

## 発注の前に確かめること

- FFC の 1 番の向き。今の基板は、このコネクタの n 番 = ER-PCBA5981-1 の CON1 の n 番と仮定している。ケーブルの種類 (両端の接点が同じ面か反対の面か) と、両端のコネクタの向きによっては、n 番が 21-n 番につながる。実物のケーブルで確かめる
- C2998680 のフットプリントは図面 (`tmp/docs/C2998680.pdf`) から作った。固定用パッドの前後の位置 (信号パッドから本体側へ約 2.26 mm) は図面の画素から読んだ値
- 74HC138 の電源は XIAO の 3.3V、FFC の VDD は XIAO の 5V (USB からそのまま)
