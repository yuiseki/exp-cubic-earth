# lt7680_multi

ER-PCBA5981-1 (LT7680A-R) + ER-TFT040-3 (ST7701S) を 1 台の XIAO ESP32-S3 から駆動するファーム。構成 1 (直結で 1 枚) と構成 2 (74HC138 で 2 枚) を同じスケッチで扱うための、基板選択の抽象。`lt7680_earth` の駆動部 (LT7680 の SPI、ST7701S の初期化、塗り、地球の面の書き込み) をそのまま使い、CS を直接叩いていた箇所を `selectLine()` に置き換えた。

## 構成ごとのビルド

配線は `WIRING.md` の構成 1、構成 2 のとおり。ビルドは同じスケッチで、旗だけが違う。

```sh
# 構成 1: XIAO ESP32-S3 直結で 1 枚
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 --output-dir build/direct \
  --build-property "compiler.cpp.extra_flags=-DBOARD_SELECT_DIRECT=1" lt7680_multi

# 構成 2: XIAO ESP32-S3 + 74HC138 で 2 枚
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 --output-dir build/hc138x2 \
  --build-property "compiler.cpp.extra_flags=-DNUM_BOARDS=2" lt7680_multi

# 書き込み (別のファームが載っていた XIAO には、起動ローダーごと merged.bin を 0x0 に)
esptool --chip esp32s3 --port $PORT --before usb-reset --after hard-reset \
  write-flash -z 0x0 build/hc138x2/lt7680_multi.ino.merged.bin
```

旗を付けないと 74HC138 で 1 枚 (`NUM_BOARDS=1`)。`-DNUM_BOARDS=3` で 3 枚 (ビルドのみ確認)。

### 構成 1: 直結で 1 枚

- `selectLine()` は D0 (LCM_SCS) と D2 (LCD_CS) を直接 Low/High にする
- 確認済み (2026-10-16 夜): メーカー推奨の起動と画素 20MHz で、USB-C の抜き差し 4/4 (本人の目視)。同じ起動で画素 10MHz は 3/3、1MHz はカメラ判定 3/3
- 基板は 1 枚なので、面の割り当て `x,n` は `0,n` だけが意味を持つ

### 構成 2: 74HC138 で 2 枚

- `selectLine()` は D0/D2/D6 に番地を置く。基板 b の LT7680 は番地 b (Y0、Y1)、パネルは 3+b (Y3、Y4)、待機は 7 (Y7)
- 共有する線: LCM_SDI/SDO/SCLK (D10/D9/D8)、LCD_DIN/LCD_SCLK (D5/D4)、LCM_RESET (D1)、BL_CONTROL (D3)、5V、GND
- 番地の切替の瞬間に隣の出力が ns 単位で落ちることがあるが、クロックが止まっている間の CS のパルスなので LT7680 も ST7701S も無視する (240x240 版で 74HC138 を使ったときと同じ扱い)
- 確認済み (2026-10-18):
  - 1 枚 (`NUM_BOARDS=1`): `select: 74HC138`、`lt7680 OK`、`boot 30-1032 ms`、STSR=0x54。USB-C の抜き差し 3/3
  - 2 枚 (`NUM_BOARDS=2`): 両方 `lt7680 OK`、`boot 30-1833 ms`。基板 0 と 1 を交互に選んで `#r` を読んでも STSR=0x54 のままで、LCM_SDO (MISO) の共有で読みは化けなかった。片方を白・片方を黒に塗り、入れ替えると入れ替わる (カメラ)。USB-C の抜き差し 3/3 で 2 枚ともすぐに映る (本人の目視)
  - 2 枚に別々の面: 基板 1 を基板 0 の左に並べ、基板 0 に面 0、基板 1 に面 3 を描くと、インドから東南アジアへ境目で地図がつながった (カメラ)
  - 面の割り当て `x,n`: `1,3` で基板 1 が面 3 になり、再起動後も面 3 で起動した。範囲外 (`1,7`、`5,0`) は断る
- 3 枚にする前に確かめること:
  - 電源: 2 枚までは XIAO の USB (VBUS) からで動いたが、余裕は測っていない。3 枚分の LT7680 + SDRAM + バックライトは 5V を外から入れる
  - MISO の共有: 3 枚目を足したら、各基板を選んで `#r` の STSR が 0x50/0x54 のままかを見る。化けるなら MISO だけ別のセレクタで切り替えるか、状態の読み返しをやめて時間待ちにする

## 命令 (先頭に `#`)

`n` の代わりに `0`〜`2` で基板を選ぶ。`A` 全基板に流れ (LT7680 リセット + パネルの SWRESET と初期化 2 回、復旧用)、`E` 選んだ基板にその基板の面 (下の「地球の面」)、`F<n>` 選んだ基板に面 n (0〜5) を一度だけ描く (割り当ては変えない)、`K`/`W` 黒/白、`r` 状態、`b` バックライト、`V` 表示用メモリを全画素読み返して地球と照合 (約 15 秒。読み返しで数画素が化けるので、終わったら `#E` で描き直す)、`S<MHz>` 画素の SPI の速さ (1〜40)、`P` パネル線の外部プルの有無 (直結モードのみ)。

## 地球の面

`earth_qsc480x6.h` は立方体の 6 面 (QSC 投影、480x480、RGB565)。

| 面 | 中心 | 主に見えるもの |
|---|---|---|
| 0 | 東経 139.767 度、赤道 | 日本、東南アジア、オーストラリア |
| 1 | 西経 130.233 度 | 太平洋、北米西岸 |
| 2 | 西経 40.233 度 | 南北アメリカ、大西洋 |
| 3 | 東経 49.767 度 | アフリカ、中東、インド |
| 4 | 北極 | |
| 5 | 南極 | |

立方体の外から見て、面 k+1 は面 k の右隣 (面 3 の右は面 0)、北極は面 0 の上、南極は面 0 の下につながる。

基板ごとの面は、シリアルに `x,n` (改行で終わる、先頭の `#` は有っても無くてもよい) を送ると変わる。基板 x に面 n を割り当ててすぐ描き、XIAO の不揮発領域 (Preferences の名前空間 `cube`、キー `f<x>`) に保存するので、再起動後もその面で起動する。保存が無ければ基板 b に面 b。起動ログの `diag: board b lt7680 OK, face n` で今の割り当てが分かる。

生成は `lt7680_earth/make_qsc_faces.py`:

```sh
cd lt7680_earth
uv run -q --no-project --with pillow --with pyproj python -I make_qsc_faces.py blue_marble_2002.jpg ../lt7680_multi/earth_qsc480x6.h --lon0 139.767 --count 4 --step 90 --size 480 --poles --name EARTH_QSC480X6
```

6 面でファームは約 3.07MB (app 領域の 91%)。

## 起動

既定はメーカー推奨どおり: 電源投入から 30ms 待つ → LCM_RESET (全基板共通) → 基板ごとに LT7680 の初期化 → ST7701S の初期化 1 回 → 表示オン → 地球。1 枚で約 1 秒。画素の SPI は既定 20MHz (`-DPIXEL_SPI_HZ=...` で変更、レジスタの読み書きは 1MHz)。以前の「1.5 秒待って流れを 2 回」は `-DBOOT_LEGACY_FLOWS=1` で残してある (LCD_CS が抜けていた頃の対症療法)。

## ISS の地上軌跡の重ね描き (`host/`、面 0 のみ)

母艦で計算し、シリアルで点を送る。XIAO 側は `#Q x y w h color` (1 行、RGB565) で四角形を塗るだけ。

```sh
cd lt7680_multi/host
uv run -q --no-project --with sgp4 --with pyproj python -I iss_track.py --minutes 180 --step 30 > ~/tmp/iss_cmds.txt
scp send_lines.py ~/tmp/iss_cmds.txt pi5-deck:tmp/
ssh pi5-deck "printf '#E' > $PORT; sleep 6; ~/.venv-esptool/bin/python tmp/send_lines.py $PORT tmp/iss_cmds.txt 0.03"
```

- `iss_track.py`: Celestrak の TLE (6 時間キャッシュ) → SGP4 → TEME から経緯度 (GMST で回す) → 面と同じ QSC 投影 (`+proj=qsc +lon_0=139.767`) で画素へ。立方体の面の判定で裏側は捨てる。過去は橙、未来は水色、現在位置は赤の印
- `send_lines.py`: 1 行ずつ 30 ms 空けて書く (まとめて流すと XIAO の受信バッファが溢れる)。pi5-deck の esptool の venv にある pyserial を使う
- ISS は 1 周 (約 92 分) ごとに約 23 度西へずれるので、前後 45 分では面に入らない時間帯がある。前後 3 時間なら 2 周分が見える
- 2026-10-16 07:4x に実機で確認 (`tmp/webcams/2026/10/16/iss-1.jpg`)
