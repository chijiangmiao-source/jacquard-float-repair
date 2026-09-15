"""提花纹板修复器：核心约束求解。

建模（CP-SAT, 0-1 整数规划）
-----------------------------
变量 x[i][j] ∈ {0,1} 为修复后纹板第 i 纬（行）第 j 列的孔位。

1. 每纬抬综数：每行恰有 K 个 1，``sum_j x[i][j] == K``。
2. 循环浮长：每列把末行与首行相接后，连续相同位长度不得超过 L。
   对环上任意连续 L+1 格，全 0 或全 1 都会形成长度 ≥ L+1 的游程，反之亦然。
   故约束等价于：每个长 L+1 的环形窗口内
       1 <= sum(x) <= L 。
   L == H 时整列本身最多 H 连等，约束自动满足，不再加窗口。
3. 改动计数：仅当输入格为 0/1 且结果不同时 g[i][j] = 1；``?`` 格不计代价。
   目标为最小化总改动数。
4. 裁决：在最少改动 C* 的全部解中，按行优先展开、0 小于 1 取字典序最小。
   2000 个变量无法用单个 int64 权值编码字典序，故把行优先位流切成 60 位
   的块，逐块以加权和最小化并固定（高位权 2^59…），由前向后保证全序字典序。
"""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model


class InfeasibleError(Exception):
    """不存在同时满足每纬容量与循环浮长的矩阵。"""


@dataclass(frozen=True)
class RepairResult:
    matrix: tuple[tuple[int, ...], ...]
    changes: int
    solve_seconds: float


def repair(
    grid: list[list[str]],
    height: int,
    width: int,
    picks: int,  # K：每纬恰有的 1 数
    max_float: int,  # L：最大循环浮长
) -> RepairResult:
    """求总改动最少、并列时字典序最小的修复矩阵。

    调用方需先用 ``validation.validate_request`` 完成全部输入校验。
    """
    import time

    H, W, K, L = height, width, picks, max_float
    model = cp_model.CpModel()

    x = [
        [model.new_bool_var(f"x_{i}_{j}") for j in range(W)]
        for i in range(H)
    ]

    # 改动指示变量 g：仅 0/1 被改变时为 1。
    cost_terms: list[cp_model.IntVar] = []
    for i in range(H):
        for j in range(W):
            v = grid[i][j]
            if v == "?":
                continue
            g = model.new_bool_var(f"chg_{i}_{j}")
            # 输入 0：g == x（结果变成 1 才算改动）
            # 输入 1：g == 1 - x（结果变成 0 才算改动）
            model.add(g == (x[i][j] if v == "0" else 1 - x[i][j]))
            cost_terms.append(g)

    changes = model.new_int_var(0, H * W, "changes")
    model.add(changes == (sum(cost_terms) if cost_terms else 0))

    # 每纬抬综数恰为 K。
    for i in range(H):
        model.add(sum(x[i]) == K)

    # 循环浮长：环上每个长 L+1 的窗口既不全 0 也不全 1。
    if L < H:
        for j in range(W):
            column = [x[i][j] for i in range(H)]
            for start in range(H):
                window = [column[(start + t) % H] for t in range(L + 1)]
                total = sum(window)
                model.add(total >= 1)  # 排除全 0（含跨首尾窗口）
                model.add(total <= L)  # 排除全 1（含跨首尾窗口）

    # 阶段 1：最少改动数。
    model.minimize(changes)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 8
    solver.parameters.max_time_in_seconds = 60.0
    t0 = time.perf_counter()
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        raise InfeasibleError("不存在同时满足每纬抬综数与循环浮长的修复矩阵")
    if status != cp_model.OPTIMAL:
        raise RuntimeError(f"求解器未返回最优解，状态 {solver.status_name(status)}")
    best_changes = solver.value(changes)

    # 固定最优改动数，进入字典序裁决。
    model.add(changes == best_changes)
    model.clear_objective()

    # 阶段 2：行优先展开，0 < 1，按 60 位一块逐块最小化并固定。
    CHUNK = 60
    total_cells = H * W
    fixed: dict[tuple[int, int], int] = {}
    n_chunks = (total_cells + CHUNK - 1) // CHUNK
    for chunk in range(n_chunks):
        lo = chunk * CHUNK
        hi = min(total_cells, lo + CHUNK)
        weighted = []
        for pos in range(lo, hi):
            i, j = divmod(pos, W)
            weighted.append((1 << (hi - 1 - pos)) * x[i][j])
        model.minimize(sum(weighted))

        lex_solver = cp_model.CpSolver()
        lex_solver.parameters.num_workers = 8
        lex_solver.parameters.max_time_in_seconds = 60.0
        status = lex_solver.solve(model)
        if status != cp_model.OPTIMAL:
            raise RuntimeError(
                f"字典序裁决第 {chunk} 块失败，状态 {lex_solver.status_name(status)}"
            )
        model.clear_objective()

        for pos in range(lo, hi):
            i, j = divmod(pos, W)
            value = lex_solver.value(x[i][j])
            fixed[(i, j)] = value
            model.add(x[i][j] == value)

    matrix = tuple(
        tuple(fixed[(i, j)] for j in range(W)) for i in range(H)
    )
    return RepairResult(
        matrix=matrix,
        changes=best_changes,
        solve_seconds=time.perf_counter() - t0,
    )
