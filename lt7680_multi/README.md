# lt7680_multi

複数の ER-PCBA5981-1 (LT7680A-R) + ER-TFT040-3 (ST7701S) を 1 台の XIAO ESP32-S3 から駆動するための、基板選択の抽象。`lt7680_earth` の駆動部 (LT7680 の SPI、ST7701S の初期化、塗り、地球の面の書き込み) をそのまま使い、CS を直接叩いていた箇所を `selectLine()` に置き換えた。

## 2 つの配線モード

| モード | ビルド | 配線 |
|---|---|---|
| 直結 (今の 1 枚構成) | `-DBOARD_SELECT_DIRECT=1` | LCM_SCS → D0、LCD_CS → D2 (`WIRING.md` の表と同じ) |
| 74HC138 (最大 3 枚) | 既定、`-DNUM_BOARDS=3` | D0/D2/D6 → 74HC138 の A0/A1/A2。Y0..Y2 → 基板 0..2 の LCM_SCS (CON1 5)、Y3..Y5 → 基板 0..2 の LCD_CS (CON1 16)、Y7 は未接続 (どれも選ばない)。G1=VCC、G2A=G2B=GND |

共有する線: LCM_SDI/SDO/SCLK (D10/D9/D8)、LCD_DIN/LCD_SCLK (D5/D4)、LCM_RESET (D1)、BL_CONTROL (D3)、5V、GND。

## 2 枚目を繋ぐ前に確かめること

- LCM_SDO (MISO) の共有: 非選択の LT7680 が SDO をハイインピーダンスにするかは未確認。状態レジスタの読み出し (FIFO 待ち、描画完了待ち) に使っているので、共有できないと読みが化ける。2 枚目を繋いだら、基板 0 を選んで `#r` の STSR が 0x50/0x54 のままかを見る。化けるなら MISO だけ別のセレクタで切り替えるか、読み返しをやめて時間待ちにする
- 電源: 3 枚分の LT7680 + SDRAM + バックライトを XIAO の 5V (USB VBUS) から取らない。5V を外部から供給する
- 74HC138 のアドレス切替時のグリッチ (隣の出力が ns 単位で落ちる) は、クロックが止まっている間の CS のパルスなので LT7680 も ST7701S も無視する想定。240x240 版 (74HC138 で 4 枚) と同じ扱い

## 命令 (先頭に `#`)

`n` の代わりに `0`〜`2` で基板を選ぶ。`A` 全基板に流れ、`E` 選んだ基板に地球、`K`/`W` 黒/白、`r` 状態、`b` バックライト。

## 確認済み

- 直結モード、1 枚: XIAO のリセット後に 2 回の流れ → 地球、`#W` → 白 (W=207)、`#E` → 地球 (2026-10-16 07:40、カメラ)
- 74HC138 モード (3 枚) はビルドのみ。実機は未接続

起動時の電源投入の問題 (cold boot で映らない) は `lt7680_earth` と同じで未解決 (`docs/STATUS.md`)。

## ISS の地上軌跡の重ね描き (`host/`)

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
