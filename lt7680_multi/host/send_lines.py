# send_lines.py: 行を 1 つずつ間隔を空けてシリアルに書く (XIAO の受信バッファを溢れさせない)。
# pi5-deck で ~/.venv-esptool/bin/python send_lines.py <port> <file> [gap_s]
import sys, time, serial
port, path = sys.argv[1], sys.argv[2]
gap = float(sys.argv[3]) if len(sys.argv) > 3 else 0.02
with serial.Serial(port, 115200, timeout=0.2) as s:
    n = 0
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#Q") is False and not line.startswith("#"):
            continue
        s.write((line + "\n").encode())
        n += 1
        time.sleep(gap)
    time.sleep(0.5)
    reply = s.read(4096).decode(errors="replace")
    bad = [l for l in reply.splitlines() if "bad" in l or "unknown" in l]
    print(f"sent {n} lines, {len(bad)} rejected", *bad[:5], sep="\n")
