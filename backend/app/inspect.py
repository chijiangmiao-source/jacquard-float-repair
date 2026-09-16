"""试打核验：以已批准的修复矩阵为基准，对设备回读矩阵做有界环形序列对齐。

业务场景
--------
修复结果投入打孔后，操作员在同一结果页粘贴设备实际回读的 0/1 矩阵、选择送料
错纬上限并发起试打核验，**无需重新求解或改写已批准纹板**。回读可从环形纹样
任意一纬开始、按正向或反向采集，送料抖动可能导致：

- **漏纬（missing_pick）**：基准某一纬在回读中整纬缺失；
- **重纬（repeated_pick）**：回读把某一纬整纬重复采集；
- **孔位不符（hole_mismatch）**：纬与纬对齐了，但个别孔打错。

设每纬宽度 W、漏纬/重纬各自不超过操作员给定上限 D（0～20），回读行数 R 必须
落在 [H-D, H+D]，否则整次核验拒绝（仅清本次核验，保留修复结果）。

建模：假设枚举 + 环形旋转 + 有界序列对齐
----------------------------------------
回读从物理纬 s 出发按方向 d 采集：正常每读一纬在环上前进一格，漏纬是“只前进
未读数”，重纬是“停顿并复读刚读的那一纬”。对每个假设 (d, s) 把基准环旋转成
以 s 为第 0 纬的线性序列（正向 ref[s],ref[s+1],…；反向 ref[s],ref[s-1],…），
回读即该线性序列经漏纬/重纬扰动得到，用经典三转移 DP 对齐：

- 匹配 (i-1,j-1)→(i,j)：代价为两行汉明距离（孔位不符数）；
- 漏纬 (i-1,j)  →(i,j)：代价 W，漏纬计数 +1（须 ≤ D）；
- 重纬 (i,j-1)  →(i,j)：代价 W，重纬计数 +1（须 ≤ D），复读的是刚消费的
  旋转下标 i-1 那一纬（环首之前按环回绕到末纬）。

只保留 |i-j| ≤ D 的带状状态。匹配代价依假设而变（旋转后配对不同），故真实
起点在无扰动回读下取得零代价，起点/方向由优化本身识别而非外部指定。

分层目标（逐层字典序最小化）
----------------------------
1. 总分：每个错纬事件（漏/重）计 W 分；每个对齐行内不同的孔计 1 分；
2. 错纬事件数（漏纬 + 重纬）；
3. 方向：正向 forward 优先于反向 reverse；
4. 起始纬号（1 基物理纬号）较小者；
5. 事件路径：每个事件记 (种类秩, 物理纬号)，种类秩
   匹配 0 < 漏纬 1 < 重纬 2，全部事件按此排序后的元组序列字典序较小者
   （匹配事件的基准/回读物理纬号相同，一个纬号即可定位）。

方向与起点在事件路径之前裁决：先用可加 DP 对每个假设求最小 (总分, 事件数)，
选出全局最优假设（方向优先、起点最小）；再对该假设做带路径裁决的 DP。

事件路径可加编码：把排序槽位 (种类秩, 物理纬号) 依次编号，越早的槽位赋越高
的 B 进制权（B=32 > 任一槽位最大重数 D ≤ 20，无进位），路径里每个事件贡献
其槽位权（同纬被重纬 k 次则贡献 k 倍）。排序元组中越早槽位的条目越多，元组
字典序越小（(a,a)＜(a,b)），故字典序最小等价于该加权和最大；权值只与事件
所在槽位有关、与边的出现顺序无关，可在环形旋转下严格可加。
"""

from __future__ import annotations

from dataclasses import dataclass

from .validation import ValidationError

MAX_BOUND = 20
MIN_H, MAX_H = 2, 200
MIN_W, MAX_W = 2, 10
_READ_ALLOWED = frozenset("01")

STATUS_MATCH = "match"
STATUS_MISMATCH = "hole_mismatch"
STATUS_MISS = "missing_pick"
STATUS_REPEAT = "repeated_pick"

DIRECTION_FORWARD = "forward"
DIRECTION_REVERSE = "reverse"

# 事件种类秩：匹配 0 < 漏纬 1 < 重纬 2。
_RANK_MATCH, _RANK_MISS, _RANK_REPEAT = 0, 1, 2

# DP 回溯边种类。
EDGE_MATCH, EDGE_MISS, EDGE_REPEAT = "M", "D", "I"


@dataclass(frozen=True)
class InspectResult:
    direction: str
    start_pick: int  # 1 基物理纬号
    score: int
    event_count: int
    miss_count: int
    repeat_count: int
    mismatch_picks: int
    mismatch_cells: int
    # mapping[i]：基准物理第 i 纬（0 基）对齐到的回读行号（1 基采集序，
    # 含该纬被重复采集的额外行）；漏纬为空元组。
    mapping: tuple[tuple[int, ...], ...]
    # 错纬事件（漏/重），按 (种类秩, 物理纬号) 排序
    events: tuple[dict, ...]
    # 逐纬时间线（消费序：匹配与漏纬按基准推进，重纬就地插入）
    timeline: tuple[dict, ...]


# ---- 核验输入校验 -------------------------------------------------------

def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_rows(payload: dict, field: str, errors: list[str]) -> list[str] | None:
    rows = payload.get(field)
    if not isinstance(rows, list) or not rows:
        errors.append(f"{field} 必须是非空的字符串数组（每行一个字符串）")
        return None
    out: list[str] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, str):
            errors.append(f"{field} 第 {idx + 1} 行必须是字符串")
            continue
        if row == "":
            errors.append(f"{field} 第 {idx + 1} 行是空行（不允许空行）")
            continue
        bad = [c for c in row if c not in _READ_ALLOWED]
        if bad:
            errors.append(
                f"{field} 第 {idx + 1} 行含非法字符 "
                f"{''.join(sorted(set(bad)))}（仅允许 0、1）"
            )
        out.append(row)
    return out


def validate_inspect_payload(payload: object) -> tuple[list[str], list[str], int]:
    """校验 /api/inspect 请求，返回 (基准矩阵行, 回读矩阵行, 上限 D)。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise ValidationError(["请求体必须是 JSON 对象"])

    bound = payload.get("max_misses")
    bound_ok = _is_int(bound) and 0 <= bound <= MAX_BOUND
    if not bound_ok:
        errors.append(f"送料错纬上限必须是 0～{MAX_BOUND} 的整数")

    ref_rows = _parse_rows(payload, "matrix", errors)
    read_rows = _parse_rows(payload, "readback", errors)

    H = W = None
    if ref_rows is not None:
        lengths = {len(r) for r in ref_rows}
        if len(lengths) > 1:
            errors.append("修复矩阵各行长度不等")
        else:
            W = next(iter(lengths))
            if not (MIN_W <= W <= MAX_W):
                errors.append(f"修复矩阵宽度必须是 {MIN_W}～{MAX_W}")
        H = len(ref_rows)
        if not (MIN_H <= H <= MAX_H):
            errors.append(f"修复矩阵高度必须是 {MIN_H}～{MAX_H}")

    if read_rows is not None:
        lengths = {len(r) for r in read_rows}
        if len(lengths) > 1:
            errors.append("回读矩阵各行长度不等（必须宽度一致）")
        elif W is not None and next(iter(lengths)) != W:
            errors.append(
                f"回读矩阵宽度 {next(iter(lengths))} 与修复矩阵宽度 {W} 不一致"
            )

    if (
        ref_rows is not None
        and read_rows is not None
        and bound_ok
        and H is not None
        and W is not None
        and len({len(r) for r in ref_rows}) == 1
        and len({len(r) for r in read_rows}) == 1
    ):
        R = len(read_rows)
        if not (H - bound <= R <= H + bound):
            errors.append(
                f"回读行数 {R} 超出 H±{bound}（{H - bound}～{H + bound}）允许范围"
            )

    if errors:
        raise ValidationError(errors)
    return ref_rows, read_rows, bound  # type: ignore[return-value]


# ---- 对齐 DP -------------------------------------------------------------

def _physical(start0: int, rotated: int, direction: str, H: int) -> int:
    """旋转序列下标 rotated 对应的物理纬号（0 基）。"""
    if direction == DIRECTION_FORWARD:
        return (start0 + rotated) % H
    return (start0 - rotated) % H


def _slot_weights(H: int, base: int) -> tuple[int, ...]:
    """2H 个错纬事件槽位各自的 B 进制权（槽位越早权越高）。

    槽位 0…H-1 为漏纬（按物理纬号升序），H…2H-1 为重纬（按物理纬号升序）。
    """
    return tuple(base ** (2 * H - 1 - slot) for slot in range(2 * H))


def _match_costs(ref: list[str], read: list[str]) -> tuple:
    """物理基准纬 × 回读行的汉明距离表：cost[p][j]。"""
    H, R = len(ref), len(read)
    return tuple(
        tuple(sum(a != b for a, b in zip(ref[p], read[j])) for j in range(R))
        for p in range(H)
    )


def _phys_map(H: int, start0: int, direction: str) -> tuple[int, ...]:
    return tuple(_physical(start0, i, direction, H) for i in range(H))


def _dp_phase1(
    cost_table: tuple,
    phys_of_i: tuple[int, ...],
    W: int,
    D: int,
) -> tuple[int, int]:
    """阶段 1：最小化 (总分, 事件数)。返回终端的 (score, events)。"""
    H, R = len(phys_of_i), len(cost_table[0]) if cost_table else 0
    INF = 10 ** 12
    # 滚动两行：prev 对应 i-1，cur 对应 i；带状列索引 j∈[i-D, i+D]。
    prev_sc = [INF] * (R + 1)
    prev_ev = [INF] * (R + 1)
    prev_mn = [0] * (R + 1)
    prev_rn = [0] * (R + 1)
    prev_sc[0] = 0
    prev_ev[0] = 0

    # i=0 基线上允许“前导重纬”（最多 D 条，均复读环上末纬 phys[H-1]）：
    # 与穷举判据及阶段 2 的 (i-1)%H 回绕保持一致；真实起点会被其他更优假设覆盖。
    wrap_phys = phys_of_i[H - 1]
    for j in range(1, min(R, D) + 1):
        prev_sc[j] = prev_sc[j - 1] + W + cost_table[wrap_phys][j - 1]
        prev_ev[j] = j
        prev_rn[j] = j

    # prev 为 i=0 行；逐行构造 i=1…H。
    for i in range(1, H + 1):
        cur_sc = [INF] * (R + 1)
        cur_ev = [INF] * (R + 1)
        cur_mn = [0] * (R + 1)
        cur_rn = [0] * (R + 1)
        lo = max(0, i - D)
        hi = min(R, i + D)
        for j in range(lo, hi + 1):
            best_s = INF
            best_e = INF
            best_mn = best_rn = 0

            if j > 0:
                ps = prev_sc[j - 1]
                if ps < INF:
                    ns = ps + cost_table[phys_of_i[i - 1]][j - 1]
                    ne = prev_ev[j - 1]
                    if (ns, ne) < (best_s, best_e):
                        best_s, best_e = ns, ne
                        best_mn, best_rn = prev_mn[j - 1], prev_rn[j - 1]

            ps = prev_sc[j]
            if ps < INF and prev_mn[j] < D:
                ns, ne = ps + W, prev_ev[j] + 1
                if (ns, ne) < (best_s, best_e):
                    best_s, best_e = ns, ne
                    best_mn, best_rn = prev_mn[j] + 1, prev_rn[j]

            if j > 0:
                ps = cur_sc[j - 1]
                if ps < INF and cur_rn[j - 1] < D:
                    ns = ps + W + cost_table[phys_of_i[i - 1]][j - 1]
                    ne = cur_ev[j - 1] + 1
                    if (ns, ne) < (best_s, best_e):
                        best_s, best_e = ns, ne
                        best_mn, best_rn = cur_mn[j - 1], cur_rn[j - 1] + 1

            cur_sc[j], cur_ev[j] = best_s, best_e
            cur_mn[j], cur_rn[j] = best_mn, best_rn
        prev_sc, prev_ev, prev_mn, prev_rn = cur_sc, cur_ev, cur_mn, cur_rn

    if prev_sc[R] >= INF:
        # R ∈ [H-D,H+D] 且漏/重各允许 D 时带内必有可行路径，到此属内部错误。
        raise RuntimeError("有界对齐未找到可行路径")
    return prev_sc[R], prev_ev[R]


def _dp_phase2(
    cost_table: tuple,
    phys_of_i: tuple[int, ...],
    W: int,
    D: int,
    weights: tuple[int, ...],
    force_score: int,
    force_events: int,
) -> list[tuple[str, int, int]]:
    """阶段 2：固定 (总分, 事件数)，最大化路径加权和并记录回溯边。

    回溯只需边种类（前驱坐标可由种类与当前 (i,j) 推出）。
    pred[i][j] ∈ {0 不可达, 1 匹配, 2 漏纬, 3 重纬}。
    """
    H, R = len(phys_of_i), len(cost_table[0]) if cost_table else 0
    INF = 10 ** 12
    rows_sc: list[list[int]] = []
    rows_ev: list[list[int]] = []
    rows_pw: list[list[int]] = []
    rows_mn: list[list[int]] = []
    rows_rn: list[list[int]] = []
    rows_pred: list[list[int]] = []

    for i in range(H + 1):
        sc = [INF] * (R + 1)
        ev = [INF] * (R + 1)
        pw = [0] * (R + 1)
        mn = [0] * (R + 1)
        rn = [0] * (R + 1)
        pred = [0] * (R + 1)
        if i == 0:
            sc[0] = 0
            ev[0] = 0
            pred[0] = 4  # 起点哨兵（真值即可达；回溯到 (0,0) 即止）
        rows_sc.append(sc)
        rows_ev.append(ev)
        rows_pw.append(pw)
        rows_mn.append(mn)
        rows_rn.append(rn)
        rows_pred.append(pred)

    def relax(i, j, kind, ns, ne, npw, nmn, nrn):
        key_new = (ns, ne, -npw)
        key_cur = (rows_sc[i][j], rows_ev[i][j], -rows_pw[i][j])
        if rows_pred[i][j] == 0 or key_new < key_cur:
            rows_sc[i][j], rows_ev[i][j], rows_pw[i][j] = ns, ne, npw
            rows_mn[i][j], rows_rn[i][j] = nmn, nrn
            rows_pred[i][j] = kind

    for i in range(H + 1):
        lo = max(0, i - D)
        hi = min(R, i + D)
        for j in range(lo, hi + 1):
            if i == 0 and j == 0:
                continue

            if i > 0 and j > 0 and rows_pred[i - 1][j - 1]:
                ns = rows_sc[i - 1][j - 1] + cost_table[phys_of_i[i - 1]][j - 1]
                relax(
                    i, j, 1,
                    ns, rows_ev[i - 1][j - 1], rows_pw[i - 1][j - 1],
                    rows_mn[i - 1][j - 1], rows_rn[i - 1][j - 1],
                )

            if i > 0 and rows_pred[i - 1][j] and rows_mn[i - 1][j] < D:
                phys = phys_of_i[i - 1]
                relax(
                    i, j, 2,
                    rows_sc[i - 1][j] + W,
                    rows_ev[i - 1][j] + 1,
                    rows_pw[i - 1][j] + weights[phys],
                    rows_mn[i - 1][j] + 1,
                    rows_rn[i - 1][j],
                )

            if j > 0 and rows_pred[i][j - 1] and rows_rn[i][j - 1] < D:
                phys = phys_of_i[(i - 1) % H]
                relax(
                    i, j, 3,
                    rows_sc[i][j - 1] + W + cost_table[phys][j - 1],
                    rows_ev[i][j - 1] + 1,
                    rows_pw[i][j - 1] + weights[H + phys],
                    rows_mn[i][j - 1],
                    rows_rn[i][j - 1] + 1,
                )

    if rows_pred[H][R] == 0:
        raise RuntimeError("路径裁决阶段未找到可行路径")
    if rows_sc[H][R] != force_score or rows_ev[H][R] != force_events:
        raise RuntimeError("路径裁决阶段未复现最优 (总分, 事件数)")

    edges_rev: list[tuple[str, int, int]] = []
    i, j = H, R
    while (i, j) != (0, 0):
        kind = rows_pred[i][j]
        if kind == 1:
            edges_rev.append((EDGE_MATCH, i - 1, j - 1))
            i, j = i - 1, j - 1
        elif kind == 2:
            edges_rev.append((EDGE_MISS, i - 1, -1))
            i -= 1
        else:
            edges_rev.append((EDGE_REPEAT, (i - 1) % H, j - 1))
            j -= 1
    edges_rev.reverse()
    return edges_rev


def run_inspect(ref: list[str], read: list[str], D: int) -> InspectResult:
    """对已校验的基准/回读矩阵执行有界环形对齐（供 API 与测试复用）。"""
    H, W = len(ref), len(ref[0])
    R = len(read)
    cost_table = _match_costs(ref, read)

    # 阶段 1：枚举 2×H 个 (方向, 起点) 假设，各求最小 (总分, 事件数)，
    # 按分层目标 (总分 → 事件数 → 方向 → 起点) 选出唯一获胜假设。
    winner = None
    for direction in (DIRECTION_FORWARD, DIRECTION_REVERSE):
        dir_rank = 0 if direction == DIRECTION_FORWARD else 1
        for start0 in range(H):
            phys_of_i = _phys_map(H, start0, direction)
            sc, ev = _dp_phase1(cost_table, phys_of_i, W, D)
            key = (sc, ev, dir_rank, start0)
            if winner is None or key < winner[0]:
                winner = (key, direction, start0, sc, ev)
            # 同方向内取得 (0,0) 的最早起点已为该方向最优：更晚起点必败。
            if sc == 0 and ev == 0:
                break
        # 正向出现总分 0、事件 0 即为全局下界，反向在同分时方向裁决也必败。
        if winner is not None and winner[1] == DIRECTION_FORWARD and winner[3] == 0 and winner[4] == 0:
            break

    _, direction, start0, best_score, best_events = winner  # type: ignore[misc]

    # 阶段 2：在获胜假设上固定最优 (总分, 事件数)，用 B 进制槽位权精确裁决
    # 排序后事件元组的字典序（B=32 > 单槽最大重数 D=20，无进位）。
    base = MAX_BOUND + 12
    weights = _slot_weights(H, base)
    phys_of_i = _phys_map(H, start0, direction)
    edges = _dp_phase2(
        cost_table, phys_of_i, W, D, weights, best_score, best_events
    )
    score, events = best_score, best_events

    mapping: list[list[int]] = [[] for _ in range(H)]
    timeline: list[dict] = []
    event_rows: list[dict] = []
    miss_count = repeat_count = mismatch_picks = mismatch_cells = 0

    for kind, rot_i, rj in edges:
        phys = _physical(start0, rot_i, direction, H)
        if kind == EDGE_MATCH:
            ref_row = ref[phys]
            read_row = read[rj]
            cells = [
                {"ref": int(a), "read": int(b), "same": a == b}
                for a, b in zip(ref_row, read_row)
            ]
            diff_count = sum(1 for c in cells if not c["same"])
            status = STATUS_MATCH if diff_count == 0 else STATUS_MISMATCH
            if diff_count:
                mismatch_picks += 1
                mismatch_cells += diff_count
            mapping[phys].append(rj + 1)
            timeline.append(
                {
                    "kind": "aligned",
                    "status": status,
                    "ref_pick": phys + 1,
                    "read_seq": rj + 1,
                    "ref_row": [int(c) for c in ref_row],
                    "read_row": [int(c) for c in read_row],
                    "cells": cells,
                    "mismatch_count": diff_count,
                }
            )
        elif kind == EDGE_MISS:
            ref_row = ref[phys]
            timeline.append(
                {
                    "kind": STATUS_MISS,
                    "status": STATUS_MISS,
                    "ref_pick": phys + 1,
                    "read_seq": None,
                    "ref_row": [int(c) for c in ref_row],
                    "read_row": None,
                    "cells": [
                        {"ref": int(c), "read": None, "same": False}
                        for c in ref_row
                    ],
                    "mismatch_count": 0,
                }
            )
            event_rows.append(
                {
                    "kind": STATUS_MISS,
                    "rank": _RANK_MISS,
                    "phys": phys + 1,
                    "ref_pick": phys + 1,
                    "read_seq": None,
                }
            )
            miss_count += 1
        else:
            read_row = read[rj]
            ref_row = ref[phys]
            rep_diff = sum(a != b for a, b in zip(ref_row, read_row))
            mismatch_cells += rep_diff
            timeline.append(
                {
                    "kind": STATUS_REPEAT,
                    "status": STATUS_REPEAT,
                    "ref_pick": phys + 1,
                    "read_seq": rj + 1,
                    "ref_row": [int(c) for c in ref_row],
                    "read_row": [int(c) for c in read_row],
                    "cells": [
                        {"ref": int(a), "read": int(b), "same": a == b}
                        for a, b in zip(ref_row, read_row)
                    ],
                    "mismatch_count": rep_diff,
                }
            )
            mapping[phys].append(rj + 1)
            event_rows.append(
                {
                    "kind": STATUS_REPEAT,
                    "rank": _RANK_REPEAT,
                    "phys": phys + 1,
                    "ref_pick": phys + 1,
                    "read_seq": rj + 1,
                }
            )
            repeat_count += 1

    # 与 DP 裁决同一口径：按 (种类秩, 物理纬号) 排序后输出错纬事件。
    event_rows.sort(key=lambda e: (e["rank"], e["phys"]))
    for e in event_rows:
        e.pop("rank")
        e.pop("phys")

    return InspectResult(
        direction=direction,
        start_pick=start0 + 1,
        score=score,
        event_count=events,
        miss_count=miss_count,
        repeat_count=repeat_count,
        mismatch_picks=mismatch_picks,
        mismatch_cells=mismatch_cells,
        mapping=tuple(tuple(m) for m in mapping),
        events=tuple(event_rows),
        timeline=tuple(timeline),
    )


def inspect_alignment(
    matrix: list[str], readback: list[str], max_misses: int
) -> InspectResult:
    """校验后以修复矩阵 ``matrix`` 为基准对回读执行有界环形对齐。"""
    ref, read, D = validate_inspect_payload(
        {"matrix": matrix, "readback": readback, "max_misses": max_misses}
    )
    return run_inspect(ref, read, D)
