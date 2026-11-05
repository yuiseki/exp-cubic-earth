"""uv run -q --no-project --with pytest --with pyserial python -m pytest -q test_play_scenes.py"""
import play_scenes as ps


def test_lines_go_through_the_scenes_and_loop():
    assert ps.lines(101, 103, loops=2) == ["#s101", "#s102", "#s103", "#s101", "#s102", "#s103"]


def test_one_scene_is_a_still():
    assert ps.lines(5, 5, loops=3) == ["#s5"]


def test_play_waits_between_lines_not_after_the_last():
    sent, slept = [], []
    ps.play(["#s1", "#s2"], 4.0, send=sent.append, sleep=slept.append)
    assert sent == ["#s1", "#s2"] and slept == [4.0]
