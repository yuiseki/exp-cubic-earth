# lt7680_multi

ER-PCBA5981-1 (LT7680A-R) + ER-TFT040-3 (ST7701S) を 1 台の XIAO ESP32-S3 から駆動するファーム。構成 1 (直結で 1 枚) と構成 2 (74HC138 で 2 枚) を同じスケッチで扱うための、基板選択の抽象。`lt7680_earth` の駆動部 (LT7680 の SPI、ST7701S の初期化、塗り、地球の面の書き込み) をそのまま使い、CS を直接叩いていた箇所を `selectLine()` に置き換えた。

## 構成ごとのビルド

配線は `WIRING.md` の構成 1、構成 2 のとおり。ビルドは同じスケッチで、旗だけが違う。

```sh
# 構成 1: XIAO ESP32-S3 直結で 1 枚
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi,PartitionScheme=max_app_8MB --output-dir build/direct \
  --build-property "compiler.cpp.extra_flags=-DBOARD_SELECT_DIRECT=1" lt7680_multi

# 構成 2: XIAO ESP32-S3 + 74HC138 で 2 枚
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi,PartitionScheme=max_app_8MB --output-dir build/hc138x2 \
  --build-property "compiler.cpp.extra_flags=-DNUM_BOARDS=2" lt7680_multi

# 構成 3: XIAO ESP32-S3 + 74HC138 で 3 枚
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi,PartitionScheme=max_app_8MB --output-dir build/hc138x3 \
  --build-property "compiler.cpp.extra_flags=-DNUM_BOARDS=3" lt7680_multi

# 書き込み (別のファームが載っていた XIAO には、起動ローダーごと merged.bin を 0x0 に)
esptool --chip esp32s3 --port $PORT --before usb-reset --after hard-reset \
  write-flash -z 0x0 build/hc138x2/lt7680_multi.ino.merged.bin
```

merged.bin は 0x0 から隙間ごと書くので、NVS (0x9000〜) の設定、面の割り当て (`#f`)、モジュールの名前 (`#m`)、`#i` が消える (2026-11-04、南極側で面がずれて、名前も空になった)。このファームが載っているモジュールを書き換えるときは、アプリだけを 0x10000 に書く:

```sh
esptool --chip esp32s3 --port $PORT --before usb-reset --after hard-reset \
  write-flash -z 0x10000 build/hc138x3/lt7680_multi.ino.bin
```

旗を付けないと 74HC138 で 1 枚 (`NUM_BOARDS=1`)。

パーティションは `max_app_8MB` (アプリ 7.9MB、OTA なし)。焼き込みの地球 (約 2.8MB) と Wi-Fi/ESP-NOW (約 0.6MB) で、既定のアプリ領域 (3.3MB) に入らない。不揮発領域 (nvs、0x9000) は既定と同じ位置と大きさなので、既定のパーティションから切り替えるときは、パーティション表とアプリだけを焼けば面の割り当てが残る:

```sh
esptool --chip esp32s3 --port $PORT --before usb-reset --after hard-reset write-flash \
  0x8000 build/hc138x3/lt7680_multi.ino.partitions.bin \
  0xe000 ~/.arduino15/packages/esp32/hardware/esp32/3.3.12/tools/partitions/boot_app0.bin \
  0x10000 build/hc138x3/lt7680_multi.ino.bin
```

`merged.bin` を 0x0 に焼くと、隙間が 0xFF で埋まって面の割り当てが消える。

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

`n` の代わりに `0`〜`2` で基板を選ぶ。`A` 全基板に流れ (LT7680 リセット + パネルの SWRESET と初期化 2 回、復旧用)、`E` 選んだ基板にその基板の面 (下の「地球の面」)、`N` 面の割り当て用に、全基板を白地にして中央に基板の名前 (基板 0、1、2 = A、B、C) を大きく、各辺の中ほどに辺の番号 (パネルを表から見て上 1、右 2、下 3、左 4) を黒で描く (文字は回さないので、文字の上がパネルの上。「A2 と B4 が接している」のように読む。`face_label.h`、`test/test_face_label.cpp`)、`F<n>` 選んだ基板に面 n (0〜5) を一度だけ描く (割り当ては変えない)、`I` 選んだ基板だけ初期化し直して面を描く (LCM_RESET は出さない)、`K`/`W` 黒/白、`r` 状態、`b` バックライト (`b0` で消す、`b1` で点ける、`b` だけなら切り替え。`backlight_cmd.h`)、`i<分>` 何もしないときにバックライトを消すまでの分 (USB の向こうにホストがいるときだけ消し、モバイルバッテリーや AC アダプターでは消さない。命令が来たら点け直す。0 で消さない、既定 10、NVS に残す。`#i` だけなら今の値。デッキにつないで放っておくと、キューブがデッキの電池を食い続けて落ちたため、`idle_backlight.h`、`test/test_idle_backlight.cpp`)、`V` 表示用メモリを全画素読み返して地球と照合 (約 15 秒。読み返しで数画素が化けるので、終わったら `#E` で描き直す)、`S<MHz>` 画素の SPI の速さ (1〜40)、`L<kHz>` レジスタの読み書きの SPI の速さ (10〜10000、既定 1000)、`P` パネル線の外部プルの有無 (直結モードのみ)。`C[<MHz>]` microSD (Sense の拡張ボードのスロット、CS は GPIO21、SPI は LT7680 と共有) を載せ、面 1 枚分 (460,800 バイト) を書いて読み返し、速さを測る (既定 10MHz)、`H<0-3>` LT7680 の SPI の SCK と MOSI の出力の強さ (ESP32-S3 の GPIO_DRIVE_CAP。起動時は `SPI_DRIVE`、既定 3。1 では `#G` を続けると数秒でレジスタが化けて面が崩れた、2026-11-03、`docs/STATUS.md`)。

hub3 では、ESP32-S3 の既定の強さ 2 のままだと、XIAO に一番近い J1 (基板 0) だけ、20MHz の画素が 1 ビットずれて大きく化けた (描くたびに 10 万画素前後、パネルに緑の帯)。SPI の線は XIAO から J1、J2、J3 の順に 1 本でつながっていて、J1 は XIAO から 7mm、J3 は 44mm。強さ 1 と 3 では 3 枚とも 0 画素、0 では数十画素 (`#V` で読み返して数えた、2026-10-28)。強さの順に良くならないので、仕組みは確かめていない。

microSD は LT7680 と SPI を分け合える。32GB の SDHC (FAT32) で、面 1 枚分の書き込みが 20MHz で約 0.36 秒、読み出しが約 0.31 秒、化けは 0 バイト。そのあと 3 枚とも `#V` で 0 画素 (2026-10-28)。

## ESP-NOW で命令を送る

起動の最後に ESP-NOW (チャンネル 1、`ESPNOW_CHANNEL`) を受け始め、起動ログに `espnow: <MAC>, channel 1` と出す。届いた塊はシリアルに打った文字と同じ命令として読む (`byte_ring.h` の輪に貯め、命令の読み取りは輪を先に、空ならシリアル)。送り手は `../espnow_bridge` (USB の 1 行をブロードキャストする中継)。画像やコマの本体 (`#U`、`#R`) はシリアルからだけ受ける。

pi5-deck に中継の XIAO (68:EE:8F:4B:1E:84) を挿し、`#N`、`#r`、`x,n,r` が届いて実行された。何もしていないときに `#r` 10 回で 10 回、`#N` で 3 枚を描いている最中に送った `#r` も 6 回で 6 回 (2026-10-28)。ブロードキャストは届いたかの確認が無いので、確実に届けたいときは返事 (シリアルのログ) を見る。

XIAO ESP32-S3 は、付属のアンテナを U.FL の端子に挿さないと、電波がほとんど飛ばない。アンテナ無しでは、周りのアクセスポイントが -80〜-95 dBm でしか見えず、ESP-NOW は近くに置いたときだけたまに届いた (ユニキャストの ACK はどちら向きも返らなかった)。2 台に付けると -50 dBm 前後になり、10 回中 10 回届いた。切り分けの命令: `#a` 周りの Wi-Fi を探して受信の強さを出す、`#p` ESP-NOW で ping を一斉送信 (中継に `rx` と出る)、`#r` に受けた ESP-NOW の数も出る。

## Wi-Fi と Web の画像 (`#j`、`#m`、`secrets.h`)

起動時に `secrets.h` (gitignore 済み、`secrets.h.example` を写して書く) の `WIFI_APS` の AP につなぐ。スキャンで見えた AP を並び順に試し、1 つも見えなければ全部を並び順に試す (隠し SSID)。中継の `../espnow_bridge` も同じ並びでつなぐので、ESP-NOW はその AP のチャンネルにそろう (expt-the-map-runs と同じ形)。自宅の AP と展示用のスマホのテザリングのように、複数書いておく。どれにもつながらなければ、ESP-NOW だけをチャンネル 1 (`ESPNOW_CHANNEL`) で使う。

```sh
#mnorth   # モジュール名を NVS に (north / south など、小文字・数字・- の 1〜15 文字)。#m だけなら今の名前
#j        # https://z.yuiseki.net/static/tmp/cubic-earth/<名前>-side-a.jpg、-b、-c を取って、基板 A、B、C に描く
```

画像は 480x480 の JPEG (512KB まで)。面の回転は使わず、パネルにそのまま描く (画像の上がパネルの上)。取りに行く先は `WEB_BASE` で変えられる。Cloudflare のキャッシュが差し替える前の画像を返さないよう、URL に毎回 `?t=<millis>` を付ける。HTTPS の証明書は確かめていない (`setInsecure`)。展開は JPEGDEC (bitbank、Apache-2.0、1.8.5、`arduino-cli lib install JPEGDEC`)。純粋な部分 (URL、名前、AP の順番) は `web_faces.h`、`test/test_web_faces.cpp`。

## microSD のシーン (`#s`、`#e`、`#w`、`host/send_scene.py`)

シーン k は microSD の `/scenes/<k>/face<f>.bin` (f = 0〜5、480x480 RGB565 リトルエンディアン、回転前。`#U` や `host/clouds.py` の `face<f>.bin` と同じ並び)。`#s<k>` で、各基板の面 (`#f` の割り当て) をシーン k から読み、回転を付けて描く。ESP-NOW で送っても同じ。

```sh
# 焼き込みの地球をシーン 0 として書き出す (6 面で約 1.9 秒)
#e0
# 母艦の clouds.py が作った face0-5.bin を、シーン 1 として書く (pi5-deck から USB、1 面約 2.3 秒)
ssh pi5-deck "~/.venv-esptool/bin/python tmp/hub3/send_scene.py $PORT tmp/cubic-clouds-20261019 1"
# 切り替え (pi5-deck の espnow_bridge に 1 行送る)
#s1
```

読んだ面は `#U` と同じ PSRAM の面 (`faceOverride`) に置くので、そのあとの `#E` や `#G` (飛行機と船) もシーンの画像を背景に使う (`#u` で焼き込みの地球に戻る)。ISS の軌跡は、母艦でシーンの 6 面に描き込んで別のシーンにする:

```sh
# 母艦: clouds.py の面 (ここでは 2026-10-19) に、前後 90 分の ISS の軌跡と今の位置を描く (過去は橙、未来は水色、今は赤)
uv run -q --no-project --with numpy --with sgp4 python -I host/scene_iss.py ~/tmp/cubic-clouds ~/tmp/cubic-scene-iss
# pi5-deck: シーン 2 として書く (このモジュールの面 4、3、0 だけ)。そのあと ESP-NOW で #s2、#G60,1,30
~/.venv-esptool/bin/python tmp/hub3/send_scene.py $PORT tmp/cubic-scene-iss 2 4 3 0
```
`scene_iss.py` の TLE と経緯度の計算は `iss_track.py` のものを使う (コピーは持たない。`iss_track.py` は pyproj を関数の中で読み込むので、上の pyproj 無しの実行で動く)。`host/test_scene_iss.py` は、関数に分ける前のスクリプトが同じ TLE と時刻で書いた 6 面の sha256 (4 組、`host/testdata/scene_iss_golden.json`) と突き合わせる。`uv run -q --no-project --with pytest --with numpy --with sgp4 --with pyproj python -m pytest -q test_scene_iss.py`


ISS の軌跡は描いた時刻のもので、動かない。ESP-NOW で `#s2` と `#G60,1,30` を送り、雲と ISS の上にラベル付きの飛行機と船 (102 個) を 60 秒動かせた (2026-10-28)。

3 枚の切り替えは約 2.7 秒 (1 枚ごとに microSD から面を読んで約 0.3 秒、描いて約 0.6 秒)。シーン 0 (地球) と 1 (2026-10-19 の雲) を、ESP-NOW で 3 回切り替えて 3 回とも 3 枚に描けた (2026-10-28)。

## 本物の飛行機と船の 1 日 (`#t`、`#J`、`flights/`)

`#G` と同じダブルバッファで、架空の飛行機と船の代わりに、ある 1 日の定期便と船を動かす。背景は今の面 (シーンを出していればシーンの画像)。

```
#t60        # microSD の /flights/day.bin を 60 秒、1 日を 120 秒で回して動かす (初回だけ PSRAM へ読む)
#t300,600   # 300 秒、1 日を 600 秒で
#t60,120,0  # 船を出さない
#J          # <WEB_BASE>/flights.bin と ships.bin を取って microSD の /flights/day.bin と ships.bin を差し替え、読み直す
```

ふだんは microSD から読み、`#J` を送ったときだけ Web から取って microSD を書き換える。Wi-Fi が無い会場でも、前に取った日が動く。`#J` は day.tmp に書いてから、形と長さ (`flight_track.h` の先頭と一致するか) を確かめて day.bin と入れ替えるので、途中で切れても前の日が残る。ESP-NOW で両モジュールに送れる。

ファイルは全球の便を持ち、モジュールは自分の面に載る分だけ描く (どの面かは `#G` と同じ QSC の投影)。15 分ごとのキーフレームの間は、モジュールが緯度経度のまま直線で補う (`flight_track.h`、`test/test_flight_track.cpp`)。印は `icons.h` の 11x11 の絵で、ラベルは出さない (数千機ぶんのスプライトはページに収まらない)。飛行機 (黄色) は上から見た形を進む向きに 8 方向で回す。向きは、半キー先 (7.5 分後) の位置をパネルの画素に直して今の位置との差から決めるので、面と基板の回転に関係なく画面の上の進む向きになる。8 方向の絵はページの上の 8 ブロックに 1 回だけ描き、全機がそこから写す。テストは `test/test_icons.cpp`。

船は `/flights/ships.bin` (形は飛行機と同じ、1 時間ごとのキーフレーム) から読み、横から見た船の絵 (白、船底がその場所の南を向くように 90 度ずつ回す。向きはラベルと同じ `southOnPanel`) で飛行機と同じ時計で動かす。ships.bin が無ければ飛行機だけ動かす。

作り方 (母艦):

```sh
# adsb.lol の globe_history (ODbL) の 1 日 (約 3.5GB) を展開して
python -I flights/globe_snapshots.py DIR 2026-11-03 snaps.json --every 15 --fill   # 定期便の 15 分ごとの位置、洋上は大円で補う
python -I flights/pack_flights.py snaps.json flights.bin --cap 60                  # どの時点でも 1 面 60 機まで
cp flights.bin /sata_hdd_24tb/www/html/static/tmp/cubic-earth/                     # そのあと ESP-NOW で #J
```

毎日の分は `flights/daily_adsblol.py` が、前日 (UTC) の分を落として抜き出し、`flights-<日付>.bin` と `flights.bin` を Web に置く (abeat の adsblol-flights-daily、毎日 15 時。adsb.lol の前日分は 12 時半ごろ出る)。取るのは GitHub のリリースの置き場からで、adsb.lol のサーバーは叩かない。回数の制限があるのはリリースを探す GitHub API (トークン無しで 1 時間 60 回、`x-ratelimit-*` ヘッダー) だけで、1 日 1 回しか呼ばず、残りが少ないか断られたらその回は止めて次の回に回す。約 3.5GB の原本は抜き出したら消し、抜き出し (約 20MB) は `/sata_hdd_24tb/adsblol/snapshots/` に残す。1 日分で約 25 分。

船は `flights/collect_ais.py` が aisstream.io (WebSocket、鍵は `~/Workspaces/.env` の `AISSTREAM_API_KEY`) を毎時 0 分から 5 分だけ全世界で受け、動いている船 (2〜40 ノット、MMSI が 2〜7 で始まる 9 桁) の最新の位置を `/sata_hdd_24tb/ais/<UTC の日>/<時>.json` に残す (abeat の ais-ships-hourly)。船は 1 時間に 0.25 度ほどしか動かず、動いている A 級は 2〜10 秒、B 級は 30 秒ごとに位置を出すので、1 時間に 5 分で足りる。船名と種類 (ShipStaticData) は 6 分おきにしか来ないので、窓をまたいで `static.json` に貯める。受信局は有志の陸上局なので、欧州 (北極の面に入る) に大きく偏り、外洋はまばら。websockets の既定の keepalive ping には aisstream が期限内に返さず、1 分半で切られたので、ping は送らず、切れたら窓の残りでつなぎ直す。

`flights/daily_ships.py` が前日 (UTC) の 24 個の窓を 1 時間ごとのスナップショットにまとめ (窓の無い時間は空のまま残して等間隔を保つ。12 個未満なら出さない)、`pack_flights.py --cap 30` で `ships-<日付>.bin` と `ships.bin` を Web に置く (abeat の ais-ships-daily、毎日 10 時 10 分)。

`--cap` は 1 面の機数の上限。1 機が 1 コマに BTE 2 回 (消すと描く) で、`#G` の測り (162 個で 1 コマ 29.2ms) から、3 面 x 60 機で 30 コマ/秒に収まる見込み。2026-11-03 の分は 65,206 便から 4,890 便、1.9MB。


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

基板ごとの面は、シリアルか ESP-NOW で `#f<x>,<n>` (改行で終わる) を送ると変わる。2026-11-03 までは `#` 無しの `x,n` も受けていたが、別の命令が崩れた残り (`#w200,1` の `#` が落ちたもの) で割り当てが書き換わったので、`#f` だけにした (`#` 無しの `x,n` は「ignored」と出して無視する)。基板 x に面 n を割り当ててすぐ描き、XIAO の不揮発領域 (Preferences の名前空間 `cube`、キー `f<x>`) に保存するので、再起動後もその面で起動する。保存が無ければ基板 b に面 b。起動ログの `diag: board b lt7680 OK, face n` で今の割り当てが分かる。

面の画像は回して映せる。`#f<x>,<n>,<r>` と送ると、基板 x に面 n を時計回りに 90 度 x r (0〜3、パネルを表から見て) 回して描き、回転も `r<x>` に保存する。`#f<x>,<n>` だけなら回転は今のまま。起動ログは `face n, turn r`。立方体の配置ごとの n と r は `simulate/` の `geometry.earth_turns` が出す (画像の上の行がパネルの上の辺、FPC と反対の辺に映ると仮定。違えば全部の r が同じだけずれる)。回転の計算は `test/test_rotate.cpp` (`g++ -std=c++17 -o /tmp/test_rotate test/test_rotate.cpp && /tmp/test_rotate`)。

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

## 名前つきのシーンと日付のコマの再生 (`#v`、`scene_names.h`)

シーンは数字のほかに名前でも置ける: `/scenes/<名前>/face<f>.bin` (名前は小文字・数字・`-` を `/` でつないだもの、63 文字まで)。数字のシーン k は名前 "k" と同じ場所なので、`#s<k>` は今までどおり。

```sh
#w<名前>,<面>                    # 面を受けて /scenes/<名前>/ に書く (send_scene.py。数字も可)
#v<組>,<から>                    # /scenes/<組>/<YYYY-MM-DD>/ のうち <から> に合うコマを 1 回描く (#vshikisai-lst,2025-07-01)
#v<組>,<から>,<まで>[,<秒>]       # 範囲のコマを <秒> (既定 5) ごとに、次の命令が来るまで繰り返す (#vshikisai-lst,2025-01,2026-10,5)
```

<から> と <まで> は YYYY、YYYY-MM、YYYY-MM-DD のどれでもよく、前の部分が合えば入る ("2025-01" は 1 月の 2 コマとも)。コマは名前の順 (日付の順)。ループ中にシリアルか ESP-NOW で命令が届くと、そのコマで止めてその命令に譲る。中継からも送れるので、キューブだけで回り続ける (母艦は要らない)。1 コマの切り替えは 2.7〜3.3 秒。

しきさいの昼の地表の温度 (GCOM-C SGLI、半月ごと、JAXA Earth の STAC) を組 `shikisai-lst` として作って書く:

```sh
# 母艦: 1 コマ 1 ディレクトリ (~/Workspaces/tmp/cubic-shikisai-lst/<YYYY-MM-DD>/)、窓に年と出典「GCOM-C/SGLI (JAXA)」
uv run -q --no-project --with numpy --with pillow --with pyproj --with tifffile python -I host/lst_year.py --set shikisai-lst --from 2025-01-01 --to 2026-10-01
# pi4-deck: 各モジュールが映す 3 面だけ (北極側 0 4 3、南極側 1 5 2)。43 コマで約 5 分
python3 send_scene.py $PORT shikisai-lst shikisai-lst 0 4 3 --tree
```

## 毎日の雲 (`host/daily_clouds.py`)

毎日 14:20 (UTC 5:20) に、abeat のジョブ `cubic-clouds-daily` が、前日 (UTC) の `clouds.py` の出力を `https://z.yuiseki.net/static/tmp/cubic-earth/clouds/<YYYY-MM-DD>/` に置く (母艦の `/sata_hdd_24tb/www/html/static/tmp/cubic-earth/clouds/`)。中身は GIBS の元画像、極の赤外 2 枚、`face0-5.bin`、`faces.png` で、1 日約 8MB。`latest.txt` に一番新しい日付。

- GIBS は 1 日 1 枚 (極軌道の衛星が昼の側を撮ってつないだもの)。日の終わりの数時間あとまで撮影分が足されるので、日が終わって 5 時間たってから取る
- 毎回、直近 3 日のうち `faces.png` の無い日を作る。隠しディレクトリで作ってから名前を変えるので、作りかけは公開されない。失敗した分は隠しディレクトリに残り、次の回で取り直す
- ログは `~/logs/clouds-daily.log`。テストは `host/test_daily_clouds.py`

```sh
# その日の 6 面を microSD のシーン 1 に書く (pi4-deck から USB)
scp -r z:/sata_hdd_24tb/www/html/static/tmp/cubic-earth/clouds/2026-11-03 pi4-deck:cubic-power/
ssh pi4-deck "cd ~/cubic-power && python3 send_scene.py $PORT 2026-11-03 1"
```

## 昼と夜と半透明の雲 (`host/scene_compose.py`)

昼は雲の無い Blue Marble、夜は NASA Black Marble 2016 (GIBS の `VIIRS_Black_Marble`、街の灯り)、その上に雲を半透明で重ねた 6 面を作る (`face0-5.bin` と `faces.png`)。microSD のシーンとして `send_scene.py` で書く。

```sh
cd lt7680_multi/host
P="uv run -q --no-project --with numpy --with pillow --with pyproj python -I scene_compose.py"
$P ~/tmp/cubic-scene-night --night-only                          # 夜だけ (街の灯り)
$P ~/tmp/cubic-scene-now --clouds 2026-10-19 --opacity 0.6       # 今の昼と夜の境目、雲 60%
$P ~/tmp/cubic-scene-day50 --clouds 2026-10-19 --opacity 0.5 --time none   # 全部昼、雲 50%
```

- 雲の不透明度は、その日の GIBS の実色が雲の無い Blue Marble よりどれだけ明るいか (明るい砂漠や雪は Blue Marble にもあるので雲に数えない)。データの無い所 (極夜など) は雲なし
- 雲は昼は白、夜は暗い灰色で重ね、`--opacity` の分だけ地面と街の灯りが透ける
- 昼と夜の境目は太陽の位置 (NOAA の簡易式) から、太陽の高度で 6 度の幅でぼかす。`--time` で時刻を指定できる
- `--layers` で、雲の上に層を重ねる (`host/layers.py`、地球の正距円筒図 4096x2048 に 2 倍の大きさで描いて縮める)。`--dim` で地面と雲を暗くして、層を目立たせる
  - `rail`: 世界の鉄道 (tile.yuiseki.net の `railways` の `railways_low`、z3 の 64 枚、© OpenStreetMap contributors、ODbL)。橙の線
  - `rivers`: 世界の川 (同じく `rivers` の `rivers_low`)。水色の線。太くすると陸地が埋まるので 1 画素で薄く
  - `airports`: OurAirports (パブリックドメイン、「Data from OurAirports」) の大きな空港と、定期便のある中くらいの空港 (3,291 件)。青緑の点
  - `population`: Kontur Population 2023-11-01 の H3 解像度 4 (71,283 セル、80.3 億人、CC BY)。セルの中心に人数を足し、人数のままぼかしてから対数にする (対数にしてからぼかすと、セルの中心の間の空いた画素が網目に残った)。対数の下半分 (人の少ない所) は暗いまま
  - タイルは `~/tmp/cubic-tiles/` にためる。Python の既定の User-Agent では tile.yuiseki.net が 403 を返すので、名前を付けて取る

```sh
P="uv run -q --no-project --with numpy --with pillow --with pyproj --with mapbox-vector-tile --with duckdb --with h3 python -I scene_compose.py"
$P ~/tmp/cubic-scene-rail --night-only --dim 0.6 --layers rail
$P ~/tmp/cubic-scene-rivers --time none --dim 0.45 --layers rivers
$P ~/tmp/cubic-scene-airports --night-only --dim 0.5 --layers airports
$P ~/tmp/cubic-scene-population --night-only --dim 0.4 --layers population
```

- GIBS の実色は、日付が新しいと合成が揃っていない (2026-10-28 に取った 10-27 は、南北アメリカの側に雲が無く、直線の境目があった)。2〜3 日前より古い日を使う
- テスト: `uv run -q --no-project --with numpy --with pillow --with pyproj --with pytest python -m pytest -q test_scene_compose.py test_layers.py`

## 正距円筒図の画像をそのまま面に (`host/equirect_scene.py`)

経緯度が等間隔の 2:1 の画像 (地球儀向けの画像の多く) を、6 面の face0-5.bin と faces.png にします。出力は scene_compose.py と同じ形で、そのまま send_scene.py で microSD に送れます。

```sh
P="uv run -q --no-project --with numpy --with pillow --with pyproj python -I equirect_scene.py"
$P Dagik_EQ_centennial/data/images/map/map_0.jpg ~/tmp/cubic-scene-eq          # 左端が 180W (Dagik Earth の配布 zip)
$P AM2SI20200925D_ITD_EQ.jpg ~/tmp/cubic-scene-seaice --west 0                  # 左端が 0 度 (国立極地研究所の Dagik Earth の画像)
```

- `--west`: 画像の左端の経度。ずれていると、faces.png の真ん中 (面 0) に日本以外が来ます。
- Dagik Earth のコンテンツは All Rights Reserved のものがあるので、画像も面もこのリポジトリには入れません。
- テスト: `uv run -q --no-project --with numpy --with pillow --with pyproj --with pytest python -m pytest -q test_equirect_scene.py`

## 雲のパラパラ漫画 (`host/clouds_hourly.py`、`host/send_frames.py`、`#R`、`#M`)

```sh
# 母艦: SSEC の全球赤外の直近 24 時間を、基板ごとの面と回転 (基板 0, 1, 2 の 面:回転) で切り出す
cd lt7680_multi/host
uv run -q --no-project --with numpy --with pillow --with pyproj python clouds_hourly.py --hours 24 --boards 3:0,4:2,0:1
scp send_faces.py send_frames.py ~/tmp/cubic-hourly/b*.bin pi5-deck:tmp/cubic-hourly/
# pi5-deck: 送る (3 基板 x 24 コマで約 3 分)。そのあと #M<ミリ秒> で再生、何か 1 文字で止まる
ssh pi5-deck "cd tmp/cubic-hourly && ~/.venv-esptool/bin/python send_frames.py $PORT . 3 24"
```

- 1 時間ごとの全球の雲は GIBS の実色には無いので、SSEC RealEarth の全球赤外 (過去 30 日、1024x512) を雲の無い Blue Marble に白く重ねる。24 時間とも同じ明るさの幅で重ねるので、コマの間で明るさが揺れない
- コマは各基板の表示用メモリのページ 8〜33 に置く (`#R<基板>,<コマ>` は受けたそばから LT7680 に流す。回転は送る側で済ませる)。再生は表示ページの切り替えだけなので、SPI をほとんど使わない

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
  - 読み込んだだけでは何も実行しない (関数に分けた)。`host/test_iss_track.py` は TLE の固定ファイル (`host/testdata/iss.tle`) と時刻を渡して、ネットワーク無しで確かめる。`host/testdata/iss_golden.json` は、関数に分ける前のスクリプトが同じ TLE と時刻で出した行 (ISS が面の上にいる場合を含む 9 組)。`uv run -q --no-project --with pytest --with sgp4 --with pyproj python -m pytest -q test_iss_track.py`
- `send_lines.py`: 1 行ずつ 30 ms 空けて書く (まとめて流すと XIAO の受信バッファが溢れる)。pi5-deck の esptool の venv にある pyserial を使う
- ISS は 1 周 (約 92 分) ごとに約 23 度西へずれるので、前後 45 分では面に入らない時間帯がある。前後 3 時間なら 2 周分が見える
- 印を動かす速さ: `#T<コマ数>,<大きさ>` は、選んだ基板の面の真ん中の行で、前の印の場所を面の画像で描き直してから新しい場所に赤い四角を塗る、を繰り返して 1 コマの時間を測る。2026-10-20 (画素 20MHz、レジスタ 1MHz) で 12 画素 2.63ms (380fps)、24 画素 3.80ms (263fps)、48 画素 8.62ms (116fps)。四角を塗るのは約 0.85ms で、残りは描き直し (窓のレジスタ設定と、64 バイトごとの FIFO の空き待ち)
- 架空の飛行機と船: `#D<秒>[,<ラベル 0/1>[,<基板あたりの飛行機>]]` (既定 30 秒、ラベル無し、基板あたり 5 機) で、飛行機 (黄色い十字) と船 (白い点、陸に当たると向きを変える、基板あたり 4 隻) を 30 コマ/秒を目標に動かす。位置は地球の上の単位ベクトルで持って大円に沿って進め、毎コマ QSC 投影 (`qsc.h`) で面と画素に直し、その面を映している基板に基板の回転を付けて描くので、面の境目をそのまままたぐ。映っていない面に出たものは見えなくなり、戻ってくればまた現れる。ラベル (架空の便名と船名、5x7 の文字 `font5x7.h`) は、その場所の南が文字の下になる向きで描く (北極の面では外向きが下)。1 機ごとに前の場所と新しい場所を囲む四角を、面の画像に印を重ねて 1 回で書く (消してから描くと、その間印が消えて画面がちらついた)。1 コマの仕事 (2026-10-20、Sense): 27 個 12.3ms、ラベル付き 20〜24ms、162 個 189ms (約 5 コマ/秒)、162 個ラベル付き 353ms。時間の大半は、1 個ごとの窓のレジスタ設定 (1MHz) と 64 バイトごとの FIFO の空き確認
- ダブルバッファ版: `#G<秒>[,<ラベル 0/1>[,<基板あたりの飛行機>[,<切り替えを待つ 0/1、既定 1>[,<コマの間のレジスタ MHz、既定 10、上限 10>]]]]`。表示用メモリ (基板ごとに 16MB) の 480x480 のページ 0 と 1 を表と裏、ページ 2 を地球の画像、ページ 3 から先をスプライト (印とラベルの絵、文字の向き 4 通り) に使う。毎コマ、裏のページで 2 コマ前に描いた四角をページ 2 から BTE で写して消し、スプライトを透明色 (0xF81F) 付きの BTE で写して描き、表示の開始アドレス (REG[20h〜23h]) を裏のページに替える。開始アドレスは書いた瞬間ではなく次の垂直同期で効くようで、替えた直後に古いページで印を消すと、まだ映っているページから印が消えてちらついた。替えた直後に垂直同期の旗 (REG[0Ch] bit4) を消し、次のコマで古いページに触る前に旗が立つのを待つと、ちらつきは消えた (本人の目視)。替える前に垂直同期を待つだけでは消えなかった。速くした点: 74HC138 の番地を GPIO のレジスタで一度に書く、1 コマの間は SPI を 10MHz で握ったままにする (20MHz では状態の読みが化けた)、BTE のレジスタは前と同じ値なら書かない、基板ごとに「切り替えが効くのを待つ → 消す → 描く → 切り替える」とまとめて待ち時間を重ねない。1 コマ (2026-10-20、ラベル付き): 27 個 5.6ms (上限 179 コマ/秒)、162 個 (飛行機 150) 29.2ms で 30 コマ/秒を保つ
- `qsc.h` は `host/qsc.py` を C に移したもの。`host/test_qsc.py` が qsc.py を PROJ (`+proj=qsc`) と、`test/test_qsc.cpp` が qsc.h を qsc.py の点 (`test/qsc_golden.h`、`host/make_qsc_golden.py` で作る) と突き合わせる (`g++ -std=c++17 -o /tmp/test_qsc test/test_qsc.cpp && /tmp/test_qsc`)
- 2026-10-16 07:4x に実機で確認 (`tmp/webcams/2026/10/16/iss-1.jpg`)

## 消灯中の消費を 1 つずつ止める (`#z`)

`#z<対象><0|1>` で、バックライトを消したあとに残る消費を 1 つずつ止める。1 で省電力、0 で元に戻す。`#z` だけなら今の状態を出す (`power_cmd.h`、`test/test_power_cmd.cpp`)。

| 命令 | 止めるもの |
|---|---|
| `#zs1` | 表示をまとめて眠らせる。バックライトを消し、液晶、LT7680 の順に眠らせる。`#zs0` で逆の順に起こし、バックライトを眠る前の状態に戻す。無線はつけたままなので、中継器から起こせる。眠っている間に `#z` 以外の命令が来たら、先に起こしてから実行する |
| `#zw1` | 無線の省電力 (`WiFi.setSleep(true)`)。ESP-NOW を取りこぼすかもしれない |
| `#zc1` | CPU を 80MHz に (`#zc0` で 240MHz) |
| `#zp1` | 液晶 ST7701S を DISPOFF と SLPIN で眠らせる (`#zp0` で SLPOUT と DISPON) |
| `#zl1` | LT7680 の PMU (0xDF) を sleep (0x83) に (`#zl0` で 0x03 にして STSR のビット 1 が落ちるのを待つ) |

起こすときは `#zl0` を先に、`#zp0` を後に送る。南極側で、眠らせる前の絵がそのまま戻った (2026-11-06、本人の目視)。
