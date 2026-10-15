# lt7680_earth

ST7701S パネル (480x480) に、地球の QSC (Quadrilateralized Spherical Cube) の 1 面を描く。
`lt7680_shell` に起動時の「初期化列を 2 回」と `#E` (地球を描く) を足したもの。

- `earth_qsc480.h` は生成物。元は NASA Blue Marble (2002、パブリックドメイン) の `blue_marble_2002.jpg`
- 作り直すとき:

```sh
uv run -q --no-project --with pillow --with pyproj python make_qsc_faces.py \
  blue_marble_2002.jpg earth_qsc480.h --count 1 --size 480 --name EARTH_QSC480
```

- 描画は REG[04h] の memory data port に RGB565 (リトルエンディアン) を 64 バイトずつ、SPI 1 MHz mode 3 で流す。480x480 で約 4.1 秒
- 起動の流れ: (LT7680 のリセットと初期化 → 表示オン → 緑で塗る → パネルの SWRESET + 初期化 ×`BOOT_PANEL_INITS`) ×`BOOT_FLOWS` → 地球を描く → バックライト
  - 既定は流れ 2 回、初期化 2 回。流れが 1 回だと XIAO のリセット後に映らない (0/8)。2 回で 10/10 (WIRING.md)
- 命令 (先頭に `#`): `E` 地球を描く、`K`/`W` 黒/白で塗る、`0` 流れを 1 回、`F0`〜`F7` 起動の条件の模倣 (実験用)、`r` 状態

ビルドと書き込みは `../lt7680_shell/` と同じ (arduino-cli、`esp32:esp32:XIAO_ESP32S3`)。
