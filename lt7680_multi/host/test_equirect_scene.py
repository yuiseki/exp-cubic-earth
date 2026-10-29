"""equirect_scene.py: any equirectangular image onto the six faces.

    uv run -q --no-project --with numpy --with pillow --with pyproj --with pytest python -m pytest -q test_equirect_scene.py
"""
import numpy as np

import clouds
import equirect_scene as es


def halves(w, h):
    """North half red, south half blue."""
    img = np.zeros((h, w, 3), dtype=np.float32)
    img[: h // 2, :, 0] = 255
    img[h // 2:, :, 2] = 255
    return img


def test_sample_reads_the_size_from_the_image():
    img = halves(64, 32)  # not clouds.W x clouds.H
    north = clouds.sample(img, np.array([0.0]), np.array([60.0]))[0]
    south = clouds.sample(img, np.array([0.0]), np.array([-60.0]))[0]
    assert north[0] > 250 and north[2] < 5
    assert south[2] > 250 and south[0] < 5


def test_faces_put_the_north_on_face_4_and_the_south_on_face_5():
    faces = es.faces(halves(256, 128), lon0=139.767, size=16)
    assert len(faces) == 6
    assert faces[4][..., 0].min() > 250  # all red
    assert faces[5][..., 2].min() > 250  # all blue
    side = faces[0]
    assert side[:4, :, 0].mean() > 250 and side[-4:, :, 2].mean() > 250  # north up on the sides


def test_write_makes_six_rgb565_faces_and_a_sheet(tmp_path):
    es.write(es.faces(halves(256, 128), lon0=0, size=8), str(tmp_path))
    for k in range(6):
        assert (tmp_path / f"face{k}.bin").stat().st_size == 8 * 8 * 2
    assert (tmp_path / "faces.png").exists()


def test_west_names_the_longitude_at_the_left_edge():
    img = np.zeros((32, 64, 3), dtype=np.float32)
    img[:, :16, 1] = 255  # green in the first quarter of the width
    assert es.shift(img, west=-180)[16, 8, 1] == 255  # already starts at 180W
    moved = es.shift(img, west=0)  # an image that starts at Greenwich: 0-90E moves to the middle
    assert moved[16, 40, 1] == 255 and moved[16, 8, 1] == 0
