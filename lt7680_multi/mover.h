#pragma once

// #D の架空の飛行機と船
struct Mover {
  int board;
  float x, y, vx, vy;
  int size;  // 印の一辺 (画素)
  bool ship;
  int px, py;  // 前のコマで描いた左上 (-1 = まだ描いていない)
};
