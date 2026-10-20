# lt7680_multi

ER-PCBA5981-1 (LT7680A-R) + ER-TFT040-3 (ST7701S) を 1 台の XIAO ESP32-S3 から駆動するファーム。構成 1 (直結で 1 枚) と構成 2 (74HC138 で 2 枚) を同じスケッチで扱うための、基板選択の抽象。`lt7680_earth` の駆動部 (LT7680 の SPI、ST7701S の初期化、塗り、地球の面の書き込み) をそのまま使い、CS を直接叩いていた箇所を `selectLine()` に置き換えた。

## 構成ごとのビルド

配線は `WIRING.md` の構成 1、構成 2 のとおり。ビルドは同じスケッチで、旗だけが違う。

```sh
# 構成 1: XIAO ESP32-S3 直結で 1 枚
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi --output-dir build/direct \
  --build-property "compiler.cpp.extra_flags=-DBOARD_SELECT_DIRECT=1" lt7680_multi

# 構成 2: XIAO ESP32-S3 + 74HC138 で 2 枚
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi --output-dir build/hc138x2 \
  --build-property "compiler.cpp.extra_flags=-DNUM_BOARDS=2" lt7680_multi

# 構成 3: XIAO ESP32-S3 + 74HC138 で 3 枚
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi --output-dir build/hc138x3 \
  --build-property "compiler.cpp.extra_flags=-DNUM_BOARDS=3" lt7680_multi

# 書き込み (別のファームが載っていた XIAO には、起動ローダーごと merged.bin を 0x0 に)
esptool --chip esp32s3 --port $PORT --before usb-reset --after hard-reset \
  write-flash -z 0x0 build/hc138x2/lt7680_multi.ino.merged.bin
```

旗を付けないと 74HC138 で 1 枚 (`NUM_BOARDS=1`)。

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

### 構成 3: 74HC138 で 3 枚

- 構成 2 に基板 2 を足す。基板 2 の LT7680 は番地 2 (Y2)、パネルは 5 (Y5)。74HC138 の出力 8 本のうち基板ごとに 2 本と待機の 1 本を使うので、3 枚が上限
- 確認済み (2026-10-18):
  - 起動ログは `boards: 3`、3 枚とも `lt7680 OK`、`boot 30-2637 ms` (電源投入から 3 枚目の地球まで約 2.6 秒、1 枚あたり約 0.8 秒)
  - USB-C の抜き差し 3/3 で 3 枚ともすぐに映る (本人の目視)
  - 3 枚とも、`#r` を 40 回読んで 40 回 STSR=0x54、CCR=0xC8、DPCR=0x40。LCM_SDO (MISO) の 3 枚共有で読みは化けない
  - 面の割り当て: 基板 0 に面 0、基板 1 に面 3、基板 2 に面 5 (南極、`2,5`) で 3 枚とも映った (カメラ)
  - 電源は XIAO の USB (VBUS) から 3 枚分 (バックライト込み) で動いている。XIAO の起動理由に電圧低下は出ていない。基板側の 5V は測っていない
- つないだ直後は基板 2 だけ起動時に初期化が失敗し、バックライトを消すと基板 2 だけリセットされる症状があった。配線を確かめ直したあとは再現していない (`WIRING.md` の「はまったところ」)

## 命令 (先頭に `#`)

`n` の代わりに `0`〜`2` で基板を選ぶ。`A` 全基板に流れ (LT7680 リセット + パネルの SWRESET と初期化 2 回、復旧用)、`E` 選んだ基板にその基板の面 (下の「地球の面」)、`F<n>` 選んだ基板に面 n (0〜5) を一度だけ描く (割り当ては変えない)、`I` 選んだ基板だけ初期化し直して面を描く (LCM_RESET は出さない)、`K`/`W` 黒/白、`r` 状態、`b` バックライト、`V` 表示用メモリを全画素読み返して地球と照合 (約 15 秒。読み返しで数画素が化けるので、終わったら `#E` で描き直す)、`S<MHz>` 画素の SPI の速さ (1〜40)、`L<kHz>` レジスタの読み書きの SPI の速さ (10〜10000、既定 1000)、`P` パネル線の外部プルの有無 (直結モードのみ)。

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

面の画像は回して映せる。`x,n,r` と送ると、基板 x に面 n を時計回りに 90 度 x r (0〜3、パネルを表から見て) 回して描き、回転も `r<x>` に保存する。`x,n` だけなら回転は今のまま。起動ログは `face n, turn r`。立方体の配置ごとの n と r は `simulate/` の `geometry.earth_turns` が出す (画像の上の行がパネルの上の辺、FPC と反対の辺に映ると仮定。違えば全部の r が同じだけずれる)。回転の計算は `test/test_rotate.cpp` (`g++ -std=c++17 -o /tmp/test_rotate test/test_rotate.cpp && /tmp/test_rotate`)。

生成は `lt7680_earth/make_qsc_faces.py`:

```sh
cd lt7680_earth
uv run -q --no-project --with pillow --with pyproj python -I make_qsc_faces.py blue_marble_2002.jpg ../lt7680_multi/earth_qsc480x6.h --lon0 139.767 --count 4 --step 90 --size 480 --poles --name EARTH_QSC480X6
```

6 面でファームは約 3.07MB (app 領域の 91%)。

## 今日の雲 (`host/clouds.py`、`host/send_faces.py`、`#U`)

```sh
# 母艦: NASA GIBS の昨日の実色 (VIIRS NOAA-20) を取り、6 面に切り出す (~/tmp/cubic-clouds/face0-5.bin と faces.png)
cd lt7680_multi/host
uv run -q --no-project --with numpy --with pillow --with pyproj python -I clouds.py
scp send_faces.py ~/tmp/cubic-clouds/face*.bin pi5-deck:tmp/cubic-clouds/
# pi5-deck: XIAO に送る
ssh pi5-deck "~/.venv-esptool/bin/python tmp/cubic-clouds/send_faces.py $PORT tmp/cubic-clouds"
```

- GIBS は登録なしで全球 4096x2048 を 1 回で取れる。昼の側だけを並べた 1 日 1 枚の合成で、極夜 (10 月は北緯約 70 度より北) と南緯約 84 度より南は真っ黒 (データ無し)
- その黒い所は、SSEC RealEarth の 1 時間ごとの全球赤外合成 (`globalir`、表記「Source: SSEC RealEarth, UW-Madison」が要る) の雲を、雲の無い Blue Marble に白く重ねて埋める。RealEarth の `/api/image` は Web メルカトル (GeoTIFF で確認) で、85 度まで、透かしなしは幅 1024 画素まで (1280 で「Size limit exceeded」の透かし)。85 度より先は 85 度の輪の平均の色。極夜では凍った海も冷たく、雲と同じく白く写る
- `#U<面>` は面の画像を 4096 バイトずつ受けて PSRAM に置き (ビルドに `PSRAM=opi` が要る)、以後その面は焼き込みの地球の代わりに使う。1 面約 2〜2.6 秒。`#u` で焼き込みに戻す

## 起動

既定はメーカー推奨どおり: 電源投入から 30ms 待つ → LCM_RESET (全基板共通) → 基板ごとに LT7680 の初期化 → ST7701S の初期化 1 回 → 表示オン → 地球。1 枚で約 1 秒。画素の SPI は既定 20MHz (`-DPIXEL_SPI_HZ=...` で変更、レジスタの読み書きは 1MHz)。以前の「1.5 秒待って流れを 2 回」は `-DBOOT_LEGACY_FLOWS=1` で残してある (LCD_CS が抜けていた頃の対症療法)。

NUM_BOARDS より少ない枚数しかつないでいないときは、LT7680 の初期化が待ち時間切れ (1 枚あたり約 1 秒) になった基板を飛ばし、つないだ基板だけ映す (シリアルに `lt7680 FAILED`)。つないでいない基板では LCM_SDO (MISO) が浮き、状態の読みが何を返すか決まらないので、画素の書き込みの待ちにも時間切れ (100ms) を入れてある。実機では未確認。

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
- 印を動かす速さ: `#T<コマ数>,<大きさ>` は、選んだ基板の面の真ん中の行で、前の印の場所を面の画像で描き直してから新しい場所に赤い四角を塗る、を繰り返して 1 コマの時間を測る。2026-10-20 (画素 20MHz、レジスタ 1MHz) で 12 画素 2.63ms (380fps)、24 画素 3.80ms (263fps)、48 画素 8.62ms (116fps)。四角を塗るのは約 0.85ms で、残りは描き直し (窓のレジスタ設定と、64 バイトごとの FIFO の空き待ち)
- 架空の飛行機と船: `#D<秒>[,<ラベル 0/1>[,<基板あたりの飛行機>]]` (既定 30 秒、ラベル無し、基板あたり 5 機) で、飛行機 (黄色い十字) と船 (白い点、陸に当たると向きを変える、基板あたり 4 隻) を 30 コマ/秒を目標に動かす。位置は地球の上の単位ベクトルで持って大円に沿って進め、毎コマ QSC 投影 (`qsc.h`) で面と画素に直し、その面を映している基板に基板の回転を付けて描くので、面の境目をそのまままたぐ。映っていない面に出たものは見えなくなり、戻ってくればまた現れる。ラベル (架空の便名と船名、5x7 の文字 `font5x7.h`) は、その場所の南が文字の下になる向きで描く (北極の面では外向きが下)。1 機ごとに前の場所と新しい場所を囲む四角を、面の画像に印を重ねて 1 回で書く (消してから描くと、その間印が消えて画面がちらついた)。1 コマの仕事 (2026-10-20、Sense): 27 個 12.3ms、ラベル付き 20〜24ms、162 個 189ms (約 5 コマ/秒)、162 個ラベル付き 353ms。時間の大半は、1 個ごとの窓のレジスタ設定 (1MHz) と 64 バイトごとの FIFO の空き確認
- ダブルバッファ版: `#G<秒>[,<ラベル 0/1>[,<基板あたりの飛行機>[,<切り替えを待つ 0/1、既定 1>[,<コマの間のレジスタ MHz、既定 10、上限 10>]]]]`。表示用メモリ (基板ごとに 16MB) の 480x480 のページ 0 と 1 を表と裏、ページ 2 を地球の画像、ページ 3 から先をスプライト (印とラベルの絵、文字の向き 4 通り) に使う。毎コマ、裏のページで 2 コマ前に描いた四角をページ 2 から BTE で写して消し、スプライトを透明色 (0xF81F) 付きの BTE で写して描き、表示の開始アドレス (REG[20h〜23h]) を裏のページに替える。開始アドレスは書いた瞬間ではなく次の垂直同期で効くようで、替えた直後に古いページで印を消すと、まだ映っているページから印が消えてちらついた。替えた直後に垂直同期の旗 (REG[0Ch] bit4) を消し、次のコマで古いページに触る前に旗が立つのを待つと、ちらつきは消えた (本人の目視)。替える前に垂直同期を待つだけでは消えなかった。速くした点: 74HC138 の番地を GPIO のレジスタで一度に書く、1 コマの間は SPI を 10MHz で握ったままにする (20MHz では状態の読みが化けた)、BTE のレジスタは前と同じ値なら書かない、基板ごとに「切り替えが効くのを待つ → 消す → 描く → 切り替える」とまとめて待ち時間を重ねない。1 コマ (2026-10-20、ラベル付き): 27 個 5.6ms (上限 179 コマ/秒)、162 個 (飛行機 150) 29.2ms で 30 コマ/秒を保つ
- `qsc.h` は `host/qsc.py` を C に移したもの。`host/test_qsc.py` が qsc.py を PROJ (`+proj=qsc`) と、`test/test_qsc.cpp` が qsc.h を qsc.py の点 (`test/qsc_golden.h`、`host/make_qsc_golden.py` で作る) と突き合わせる (`g++ -std=c++17 -o /tmp/test_qsc test/test_qsc.cpp && /tmp/test_qsc`)
- 2026-10-16 07:4x に実機で確認 (`tmp/webcams/2026/10/16/iss-1.jpg`)
