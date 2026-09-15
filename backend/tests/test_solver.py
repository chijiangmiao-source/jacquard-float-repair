"""以小规模穷举为判据，核对最优改动数与字典序裁决。"""

from __future__ import annotations

import itertools
import random

import pytest

from app.solver import InfeasibleError, repair
from app.validation import classify_cell


def cyclic_runs(column: list[int]) -> int:
    """环上（末格与首格相接）最长连续相同位长度。"""
    H = len(column)
    if all(v == column[0] for v in column):
        return H
    start = next(t for t in range(H) if column[t] != column[(t - 1) % H])
    best = cur = 1
    for t in range(1, H):
        if column[(start + t) % H] == column[(start + t - 1) % H]:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def brute_optimal(H, W, K, L, grid):
    """枚举所有每纬恰有 K 个 1 的矩阵，返回 (改动数, 行优先位串) 或 None。"""
    patterns = [p for p in range(1 << W) if p.bit_count() == K]
    best = None
    for rows in itertools.product(patterns, repeat=H):
        cost = 0
        for i, p in enumerate(rows):
            for j in range(W):
                v = grid[i][j]
                if v in "01" and int(v) != ((p >> j) & 1):
                    cost += 1
        valid = True
        for j in range(W):
            col = [(rows[i] >> j) & 1 for i in range(H)]
            if cyclic_runs(col) > L:
                valid = False
                break
        if not valid:
            continue
        bits = tuple((rows[i] >> j) & 1 for i in range(H) for j in range(W))
        key = (cost, bits)
        if best is None or key < best:
            best = key
    return best


def case_params(rng: random.Random):
    H = rng.randint(2, 5)
    W = rng.randint(2, 4)
    K = rng.randint(0, W)
    L = rng.randint(1, H)
    grid = [[rng.choice("01?") for _ in range(W)] for _ in range(H)]
    return H, W, K, L, grid


def test_exhaustive_matches_brute_force():
    rng = random.Random(20260915)
    for trial in range(240):
        H, W, K, L, grid = case_params(rng)
        expected = brute_optimal(H, W, K, L, grid)
        if expected is None:
            with pytest.raises(InfeasibleError):
                repair(grid, H, W, K, L)
            continue
        result = repair(grid, H, W, K, L)
        flat = tuple(result.matrix[i][j] for i in range(H) for j in range(W))
        assert result.changes == expected[0], (H, W, K, L, grid)
        assert flat == expected[1], (H, W, K, L, grid)
        # 解的内部一致性：每纬恰有 K 个 1。
        assert all(sum(row) == K for row in result.matrix)
        # 循环浮长复核。
        assert all(
            cyclic_runs([result.matrix[i][j] for i in range(H)]) <= L
            for j in range(W)
        )


def test_unknown_cells_are_free():
    # 两个候选都是 0 改动（? 取值不计），字典序最小者首位应取 0。
    grid = [["?", "?"]] * 2
    r = repair(grid, 2, 2, 1, 2)
    assert r.changes == 0
    assert r.matrix[0] == (0, 1)  # 行内字典序最小且恰含 1 个 1
    assert r.matrix[1] == (0, 1)


def test_fixed_change_costs_one():
    # 10 / 10，K=1 可行；要求 01 / 01 则需改动 2 个固定 1（补孔不计此例）。
    grid = [["1", "0"], ["1", "0"]]
    assert repair(grid, 2, 2, 1, 2).changes == 0
    r = repair(grid, 2, 2, 1, 1)  # H=2 L=1 需逐列交替
    # 两个可行方向 (10,01) 与 (01,10) 都是 2 改动；字典序取首格为 0 的后者。
    assert r.changes == 2
    assert r.matrix == ((0, 1), (1, 0))


def test_seam_only_violation_is_excluded():
    # 列 0 = 1,1,0,1：所有不含跨首尾的长度 3 窗口均混合，
    # 唯有跨首尾窗口 {末行,首行,第二行}=1,1,1 超限（L=2）。
    grid = [["1", "0"], ["1", "0"], ["0", "1"], ["1", "0"]]
    # 原矩阵每纬恰含 1 个 1，若忽略末行-首行接缝，会当作 0 改动解；
    # 接缝超限使该候选被排除，最优被迫改动 2 格（穷举核对）。
    r = repair(grid, 4, 2, 1, 2)
    assert r.changes == 2
    assert r.matrix == ((0, 1), (1, 0), (0, 1), (1, 0))
    # L=3 时跨首尾游程恰为 3，原纹板 0 改动即可保留。
    assert repair(grid, 4, 2, 1, 3).changes == 0


def test_odd_cycle_infeasible():
    # H=3 奇环、L=1 要求逐格交替，无解。
    with pytest.raises(InfeasibleError):
        repair([["?"] * 2 for _ in range(3)], 3, 2, 1, 1)


def test_constant_column_cases():
    # K=0 全 0 列，环上 H 连等：L<H 无解，L=H 有解。
    with pytest.raises(InfeasibleError):
        repair([["?"] * 3 for _ in range(5)], 5, 3, 0, 4)
    assert repair([["?"] * 3 for _ in range(5)], 5, 3, 0, 5).changes == 0
    # K=W 全 1 列同理。
    with pytest.raises(InfeasibleError):
        repair([["?"] * 2 for _ in range(4)], 4, 2, 2, 3)


def test_classify_cell():
    assert classify_cell("1", 1) == "original_hole"
    assert classify_cell("1", 0) == "removed_hole"
    assert classify_cell("0", 1) == "added_hole"
    assert classify_cell("0", 0) == "kept_blank"
    assert classify_cell("?", 1) == "unknown_hole"
    assert classify_cell("?", 0) == "unknown_blank"
