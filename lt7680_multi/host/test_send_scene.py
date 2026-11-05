"""uv run -q --no-project --with pytest --with pyserial python -m pytest -q test_send_scene.py"""
import send_scene


class FakeXiao:
    """Answers "#r" with a status line, but only once it has booted (after `boot_reads` reads)."""

    def __init__(self, boot_reads):
        self.boot_reads = boot_reads
        self.out = b""
        self.written = []

    def write(self, data):
        self.written.append(data)
        if data == b"#r\n" and self.boot_reads <= 0:
            self.out += b"cmd r: board 0 STSR=0x54\r\n"

    @property
    def in_waiting(self):
        return len(self.out)

    def read(self, n=1):
        self.boot_reads -= 1
        n = max(n, 1)
        data, self.out = self.out[:n], self.out[n:]
        return data

    def reset_input_buffer(self):
        self.out = b""


def test_ready_probes_until_the_shell_answers(monkeypatch):
    monkeypatch.setattr(send_scene.time, "sleep", lambda s: None)
    x = FakeXiao(boot_reads=5)  # still booting (just plugged in): the first probes get no answer
    assert send_scene.wait_ready(x, timeout=20)
    assert x.written.count(b"#r\n") >= 2


def test_ready_gives_up_if_the_shell_never_answers(monkeypatch):
    monkeypatch.setattr(send_scene.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000))
    monkeypatch.setattr(send_scene.time, "time", lambda: next(clock))
    assert not send_scene.wait_ready(FakeXiao(boot_reads=10**9), timeout=20)


def test_jobs_for_one_scene_keep_the_old_numbered_form(tmp_path):
    assert send_scene.jobs(str(tmp_path), "101", [0, 3], tree=False) == [("101", 0, str(tmp_path / "face0.bin")), ("101", 3, str(tmp_path / "face3.bin"))]


def test_jobs_for_a_tree_name_each_dated_frame_under_the_set(tmp_path):
    for d in ("2025-01-16", "2025-01-01", "src", "sheet.png"):
        (tmp_path / d).mkdir() if d != "sheet.png" else (tmp_path / d).write_bytes(b"")
    js = send_scene.jobs(str(tmp_path), "shikisai-lst", [1], tree=True)
    assert [j[:2] for j in js] == [("shikisai-lst/2025-01-01", 1), ("shikisai-lst/2025-01-16", 1)]
    assert js[0][2] == str(tmp_path / "2025-01-01" / "face1.bin")
