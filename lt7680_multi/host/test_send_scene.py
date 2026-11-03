"""uv run -q --no-project --with pytest --with pyserial python -m pytest -q test_send_scene.py"""
import send_scene


class FakePort:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.read_log = []

    @property
    def in_waiting(self):
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, n=1):
        if not self.chunks:
            return b""
        c = self.chunks.pop(0)
        self.read_log.append(c)
        return c


def test_settle_waits_for_the_shell_after_a_reset(monkeypatch):
    monkeypatch.setattr(send_scene.time, "sleep", lambda s: None)
    port = FakePort([b"ESP-ROM:esp32s3\r\nrst:0x15 (USB_UART_CHIP_RESET)\r\n", b"diag: board 0 lt7680 OK\r\n", b"shell ready\r\n"])
    assert send_scene.settle(port) is True
    assert port.chunks == []


def test_settle_does_not_wait_when_the_xiao_kept_running(monkeypatch):
    monkeypatch.setattr(send_scene.time, "sleep", lambda s: None)
    port = FakePort([])
    assert send_scene.settle(port) is False
