#pragma once

// #D の架空の飛行機と船。位置は地球の上の単位ベクトル p、進む向きは p に直交する単位ベクトル d で、
// 1 コマごとに大円に沿って speed (ラジアン) 進む。画面には、その点が載る面を映している基板に描く
struct Mover {
  float p[3], d[3];
  float speed;
  int size;  // 印の一辺 (画素)
  bool ship;
  int board;   // 描いている基板 (-1 = どの基板の面にも載っていない)
  int px, py;  // 描いている左上 (パネルの座標)
};
