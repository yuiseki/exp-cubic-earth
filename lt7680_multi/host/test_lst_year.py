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
