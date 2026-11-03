#pragma once

// #b の引数: '0' で消す、'1' で点ける、それ以外 (行の終わり、何も無い) なら今までどおり切り替え。
// 切り替えだけだと、送る前の状態が分からないと結果も分からない (2026-11-03、転送中に消したくなった)。
// next は #b の次の文字 (無ければ -1)。test/test_backlight_cmd.cpp で確かめる
inline bool takesArg(int next) { return next == '0' || next == '1'; }
inline bool backlightAfter(bool now, int next) { return takesArg(next) ? next == '1' : !now; }
