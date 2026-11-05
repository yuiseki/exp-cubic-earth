# espnow_bridge

USB シリアルで受けた 1 行 (改行まで、最大 250 バイト) を、ESP-NOW (チャンネル 1) でブロードキャストする中継。受け手は `../lt7680_multi` で、届いた行をシリアルに打った命令と同じに扱う。2 つのモジュールに同じ命令を同時に送れる。

```sh
cp secrets.h.example secrets.h   # lt7680_multi と同じ AP の並びを書く
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 --output-dir build espnow_bridge
esptool --chip esp32s3 --port $PORT --before usb-reset --after hard-reset write-flash 0x0 build/espnow_bridge.ino.merged.bin
```

- 送った行ごとに `sent ok: <行>` (送信の待ち行列に入った) か `sent FAIL: <行>` を返す。ブロードキャストには届いたかの確認が無い
- ESP-NOW で届いた行は `rx <MAC>: <行>` と出す。送ったあとに `delivered ok/FAIL to <MAC>` (ブロードキャストは電波に乗ったか、ユニキャストは相手の ACK が返ったか)
- `!AA:BB:CC:DD:EE:FF <行>` はその MAC だけに送る (ユニキャスト。電波が届いているかの切り分け用)
- `?` だけの行は、中継自身のチャンネルと、周りの Wi-Fi の受信の強さを出す
- 付属のアンテナを U.FL に挿す。挿さないと電波がほとんど飛ばない (`../lt7680_multi/README.md`)
- 2026-10-28 から、pi5-deck に XIAO ESP32-S3 `68:EE:8F:4B:1E:84` を挿して使っている (焼く前のフラッシュ全域は pi5-deck の `~/tmp/1e84-backup/flash_8MB.bin`)

## 電池がどれだけ持つか (`battery_watch.py`)

電池で動かしているモジュールに、60 秒ごとに描画の負荷と `#p` を、XIAO の MAC あてに 1 台ずつ続けて送り、モジュールごとの ACK と ping の返りを CSV に 1 行ずつ書く。返らなくなった時刻が、電池の切れた時刻。MAC はいくつでも並べられる。ファームウェアは変えなくてよい (ブリッジが `rx <MAC>: ...` と送り主を付けて出すので、どのモジュールの ping かを区別できる)。

```sh
# 母艦 (systemd のユーザー単位で、ssh を切っても続く)。pi5-deck は自分の電池で先に止まることがあった
systemd-run --user --unit cube-battery --collect ~/.venv-esptool/bin/python -u battery_watch.py \
  /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_68:EE:8F:4B:1E:84-if00 \
  ~/logs/cube-battery-YYYYMMDD.csv B8:F8:62:F8:DB:A0 8C:BF:EA:8F:3F:38 --until YYYY-MM-DDT12:00
```

負荷は `--loads` の中から周ごとにランダムに選ぶ (既定 `G` だけ): `t` 本物の飛行機と船 `#t40` (いちばん重い)、`G` 架空の飛行機と船 `#G40,1,30`、`v` しきさいのシーンを microSD から 3 秒ごとに描き直す `#vshikisai-lst,<ランダムな月>,2026-10,3` (次の `#p` で止まる)、`j` Wi-Fi で Web の画像 `#j`。`--seed` で選び方を固定できる。

```sh
# ランダムな重い描画で、両モジュールが止まるまで
systemd-run --user --unit cube-battery --collect /usr/bin/python3 -u battery_watch.py \
  /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_68:EE:8F:4B:1E:84-if00 \
  ~/logs/cube-battery-YYYYMMDD.csv B8:F8:62:F8:DB:A0 8C:BF:EA:8F:3F:38 --loads tGvj
```

列は `time`、`load` (その周の負荷の種類) と、モジュールごと (MAC の末尾 4 桁) に `ack_G_xxxx` (負荷の命令の ACK)、`ack_p_xxxx` (#p の ACK)、`ping_xxxx` (モジュールからの ping が届いたか、ファームウェアが動いている印)。テストは `uv run -q --no-project --with pyserial --with pytest python -m pytest -q test_battery_watch.py`。ACK は無線が受けた印で、ファームウェアが固まっていても返ることがある。
