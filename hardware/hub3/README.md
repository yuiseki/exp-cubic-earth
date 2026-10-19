# hub3

XIAO ESP32-S3 (ピンソケットで挿す)、74HC138、20 ピン 1.0mm の FFC コネクタ 3 個を載せた 44 x 44 mm の 2 層基板。ER-PCBA5981-1 を 3 枚つなぎ、`lt7680_multi` の構成 3 (`-DNUM_BOARDS=3`) と同じ配線にする (`WIRING.md`)。

- J1 (LCD0、左の辺)、J2 (LCD1、上の辺)、J3 (LCD2、右の辺): Ckmtw F-FPC1M20P-B310 下接 (LCSC C132515)。口は基板の外を向き、基板の辺にそろう。3 個は基板の中心のまわりに 90 度ずつ回した同じ置き方
- U2: XIAO ESP32-S3。USB-C は下の辺 (FFC の無い辺) に向く
- U1: 74HC138 (SOIC-16、LCSC C2674688)。A, B, C = D0, D2, D6。基板 b の LCM_SCS は Yb、LCD_CS は Y(3+b)、Y6 と Y7 は空き
- C1 100nF (74HC138 の 3.3V)、C2 10uF (XIAO の 5V ピンのそば)
- 角に M2 の穴 4 個

## 作り方

すべてスクリプトから作る。回路図と基板を手で直したら、次に `make.py` を流すと上書きされる。

```sh
/usr/bin/python3 make.py    # 回路図、部品を置いた基板、ライブラリ (KiCad 10 の pcbnew モジュールを使う)
/usr/bin/python3 route.py   # Freerouting で配線し、GND のベタを塗る
./check.sh                  # ERC、DRC (回路図との突き合わせ込み)、test_hub3.py。どれも 0 件で通る
/usr/bin/python3 fab.py     # JLCPCB 用: build/fab/ にガーバーとドリルの zip、BOM、部品配置 (CPL)
```

- 部品と網の表は `make.py` の先頭にあり、回路図と基板の両方がそこから作られる
- `test_hub3.py` は `make.py` とは別に、`WIRING.md` の配線表から各パッドの網を確かめる
- Freerouting は Linux 向けの実行環境同梱版 (`freerouting-2.4.1-linux-x64.zip`) を `~/.local/share/freerouting/2.4.1/` に置いて使う。jar 単体は Java 25 が要る
- 配線するときは GND のベタを外し、GND も線で引いてからベタを戻す。ベタを残したまま渡すと、Freerouting は GND を引かず、表のベタが島に分かれる
- Freerouting は、`make.py` で作るたびに違う配線を返し、ときどき島や未接続を残したり、電源の線を FFC のパッドの手前で長く細らせたりする。`route.py` は、KiCad の DRC が 0 件で、+5V と +3V3 の 0.6 mm 未満の区間が合わせて 7.5 mm (FFC コネクタ 1 個あたり約 2.5 mm) 以下になるまで、最大 8 回やり直す。Freerouting は同じ DSN なら設定や網の順を変えても同じ結果を返すが、`make.py` が作るたびに部品の内部 ID が変わって DSN も変わるので、やり直すときは `make.py` から作り直す。1 回ごとに別のプロセスで動かす (pcbnew の SWIG は、同じプロセスで基板を読み直して編集すると落ちる)
- 部品配置 (CPL) とガーバーの原点は基板の左下の角。SOIC-16 は JLCPCB の 0 度が KiCad と 90 度ずれるので、CPL では 90 度引いている (`fab.py` の `JLC_ROTATION_OFFSET`、JLCPCB の確認画面で見つけた)。BOM と CPL は LCSC の番号がある部品だけ (U1、C1、C2、J1〜J3)。XIAO のピンソケット 2 個は手ではんだ付けする

## 発注の前に確かめること

- FFC の 1 番の向き。この基板は「コネクタの n 番 = ER-PCBA5981-1 の CON1 の n 番」としている。根拠: 今つないでいる変換基板 (FPC-20P 1.0MM) のコネクタは C132515 と同じ下接で (本人の確認、2026-10-19)、1 番も口から見て同じ側 (口を上にして左) にある (写真のシルクの 10 と 20 の位置から読んだ)。その変換基板で、同じケーブル (両端の接点が同じ面) を裏返さずに使って「変換基板の j 番 = CON1 の j 番」で動いている。ケーブルを裏返すと n 番が 21-n 番につながる
- C132515 のフットプリントは、JLCPCB の EasyEDA にある同じ部品のフットプリント (FPC-SMD_P1.00-20P_XJ-CLS) のパッドの数値で作った。JLCPCB の部品配置の確認画面で、J1〜J3 の向きを確かめる
- 74HC138 の電源は XIAO の 3.3V、FFC の VDD は XIAO の 5V (USB からそのまま)
