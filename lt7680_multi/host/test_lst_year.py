"""uv run -q --no-project --with pytest --with numpy --with pillow --with pyproj python -m pytest -q test_lst_year.py"""
import numpy as np

import lst_year as ly


def test_half_months_are_the_24_catalog_names_in_order():
    hm = ly.half_months()
    assert len(hm) == 24
    assert hm[:3] == ["01-01", "01-16", "02-01"]
    assert hm[-1] == "12-16"


def test_label_says_which_half_of_which_month():
    assert ly.label("07-01") == "7月前半"
    assert ly.label("12-16") == "12月後半"


def test_item_urls_name_the_west_and_east_halves():
    w, e = ly.tif_urls("07-01")
    assert w.endswith("/07-01/0/W180.00-E000.00/W180.00-S90.00-E000.00-N90.00-LST_2012_2021.tif")
    assert e.endswith("/07-01/0/E000.00-E180.00/E000.00-S90.00-E180.00-N90.00-LST_2012_2021.tif")


def test_celsius_from_dn_with_nodata_as_nan():
    c = ly.celsius(np.array([0, 15000, 16000], dtype=np.uint16))
    assert np.isnan(c[0])
    assert abs(c[1] - (15000 * 0.02 - 273.15)) < 1e-3
    assert c[2] > c[1]


def test_join_puts_west_on_the_left():
    w = np.full((2, 3), 1, dtype=np.uint16)
    e = np.full((2, 3), 2, dtype=np.uint16)
    g = ly.join(w, e)
    assert g.shape == (2, 6) and g[0, 0] == 1 and g[0, -1] == 2


def test_colours_run_cold_blue_to_hot_red_and_clip_at_the_ends():
    rgb = ly.colours(np.array([-80.0, ly.T_MIN, 0.0, ly.T_MAX, 90.0]))
    assert (rgb[0] == rgb[1]).all() and (rgb[3] == rgb[4]).all()  # clipped
    cold, hot = rgb[1], rgb[3]
    assert cold[2] > cold[0]  # blue over red
    assert hot[0] > hot[2]  # red over blue


def test_picture_keeps_the_sea_from_the_base_and_paints_land():
    lst = np.array([[np.nan, 40.0]], dtype=np.float32)
    base = np.full((1, 2, 3), 7.0, dtype=np.float32)
    img = ly.picture(lst, base)
    assert (img[0, 0] == 7.0).all()
    assert (img[0, 1] == ly.colours(np.array([40.0]))[0]).all()


def test_spot_avoids_land_and_stays_inside():
    land = np.zeros((100, 100), dtype=bool)
    land[:, :60] = True  # land on the left, sea on the right
    x, y = ly.spot(land, 30, 20, margin=4)
    assert x >= 60 and x + 30 <= 100 - 4 and 4 <= y and y + 20 <= 100 - 4
    assert not land[y:y + 20, x:x + 30].any()


def test_spot_takes_the_least_land_when_no_place_is_clear():
    land = np.ones((50, 50), dtype=bool)
    land[30:45, 5:25] = False  # one patch of sea
    x, y = ly.spot(land, 20, 15, margin=2)
    assert land[y:y + 15, x:x + 20].sum() == 0


def test_spot_goes_to_the_preferred_corner_among_clear_places():
    land = np.zeros((100, 100), dtype=bool)
    land[60:, 60:] = True  # the lower right corner is land
    x, y = ly.spot(land, 20, 10, margin=2, toward=(1, 1))
    assert not land[y:y + 10, x:x + 20].any()
    assert x + 20 >= 90 or y + 10 >= 90  # pushed against the right or the bottom edge
    x2, y2 = ly.spot(np.zeros((100, 100), dtype=bool), 20, 10, margin=2, toward=(1, 0))
    assert (x2, y2) == (100 - 2 - 20, 2)  # top right


def test_every_side_face_has_a_corner():
    assert len(ly.CORNERS) == 4 and ly.CORNERS[0] == (1, 0) and ly.CORNERS[1:] == [(1, 1)] * 3


def test_dated_half_months_run_from_the_first_to_the_last_inclusive():
    d = ly.dated_half_months("2025-01-01", "2026-10-01")
    assert d[:3] == ["2025-01-01", "2025-01-16", "2025-02-01"]
    assert d[-2:] == ["2026-09-16", "2026-10-01"]
    assert len(d) == 43


def test_dated_label_and_urls_for_shikisai():
    s = ly.SETS["shikisai-lst"]
    assert s.label("2025-10-16") == "2025年10月後半"
    w, e = s.urls("2025-07-01")
    assert w.endswith("L3-LST.daytime.v3_global_half-monthly/2025-07/01/0/W180.00-E000.00/W180.00-S90.00-E000.00-N90.00-LST.tiff")
    assert e.endswith("/2025-07/01/0/E000.00-E180.00/E000.00-S90.00-E180.00-N90.00-LST.tiff")
    assert "JAXA" in s.credit


def test_shikisai_nodata_is_65535_and_the_normal_s_is_0():
    dn = np.array([0, 65535, 15000], dtype=np.uint16)
    c = ly.SETS["shikisai-lst"].celsius(dn)
    assert np.isnan(c[1]) and not np.isnan(c[0]) and not np.isnan(c[2])
    c = ly.SETS["modis-normal"].celsius(dn)
    assert np.isnan(c[0]) and not np.isnan(c[1])


def test_the_normal_keeps_its_numbered_frames_and_labels():
    s = ly.SETS["modis-normal"]
    assert s.label("07-01") == "7月前半"
    assert ly.frame_dir(s, "07-01", 13) == "13" and ly.frame_dir(ly.SETS["shikisai-lst"], "2025-07-01", 13) == "2025-07-01"
