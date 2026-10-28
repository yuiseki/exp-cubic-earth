# espnow_bridge

USB シリアルで受けた 1 行 (改行まで、最大 250 バイト) を、ESP-NOW (チャンネル 1) でブロードキャストする中継。受け手は `../lt7680_multi` で、届いた行をシリアルに打った命令と同じに扱う。2 つのモジュールに同じ命令を同時に送れる。

```sh
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 --output-dir build espnow_bridge
esptool --chip esp32s3 --port $PORT --before usb-reset --after hard-reset write-flash 0x0 build/espnow_bridge.ino.merged.bin
```

- 送った行ごとに `sent ok: <行>` (送信の待ち行列に入った) か `sent FAIL: <行>` を返す。ブロードキャストには届いたかの確認が無い
- ESP-NOW で届いた行は `rx <MAC>: <行>` と出す
- 2026-10-28 から、pi5-deck に XIAO ESP32-S3 `68:EE:8F:4B:1E:84` を挿して使っている (焼く前のフラッシュ全域は pi5-deck の `~/tmp/1e84-backup/flash_8MB.bin`)
