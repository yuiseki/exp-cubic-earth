# simulate

立方体の組み方を 3MF にして、3D ビューワーで見るためのスクリプト。寸法は `docs/DIMENSIONS.md`。

```sh
# 1. メーカーの STEP (ER-TFT040-3-6011.zip の中身) を、パネルと基板の STL に分ける (約 40 秒)
uv run --no-project --with gmsh --with numpy --with numpy-stl python step_parts.py ER-TFT040-3-6011.STEP

# 2. 2 つの角モジュールで立方体を組み、合体と分解の 3MF を書く
uv run --no-project --with numpy --with numpy-stl python cube.py --fpc top=-y,A=-z,B=-z

# テスト
uv run --no-project --with numpy --with pytest python -m pytest -q test_geometry.py
```

- 出力は `build/` (git に入れない。メーカーの 3D モデルから作った形を含むため)
- 1 つ目のモジュールは天面 (+z)、A (-y)、B (+x) の 3 面。2 つ目は同じモジュールを (1, 1, 0) の軸のまわりに半回転したもので、底面 (-z)、C (-x)、D (+y) になる
- `--fpc` は 1 つ目のモジュールの各面について、FPC の出る辺が向く方向 (世界の軸)。2 つ目は回転で決まる
- 面は FPC を折って基板をパネルの裏に重ねた状態 (基板は FPC の辺から 20mm)。FPC と FFC は箱で近似している。FFC は CON1 からパネルの辺の 2mm 先までを描く
- `--edge` を省くと、2 つの面の部品が重ならない最小の辺の長さ (向かい合うガラスの間) で組む。今は 6 面ともパネルの中心を立方体の中心から同じ距離に置くだけで、角で一方の面が他方の縁に重なる組み方はまだ入れていない
- 実行すると、各面の FFC がどの面の側へ出ていくかを表示する
- `cube.py --search` は、1 つ目のモジュールの 3 面の向き 64 通りについて、FFC の行き先、3 本とも自分のモジュールに留まるか、1 枚の面を角のまわりに 120 度ずつ回した形か (外から角を見て時計回りか反時計回りか)、最小の辺の長さを並べる。3 本とも留まるのは 8 通り、そのうち 120 度ずつ回した形は 2 通り (`top=-y,A=+x,B=+z` が時計回り、`top=-x,A=-z,B=+y` が反時計回り)
