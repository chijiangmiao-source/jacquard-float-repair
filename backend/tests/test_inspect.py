"""试打核验：小规模穷举路径复核分层目标与裁决 + 接口测试。"""

from __future__ import annotations

import itertools
import random

import functools

import pytest
from fastapi.testclient import TestClient

from app.inspect import (
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    EDGE_MATCH,
    EDGE_MISS,
    EDGE_REPEAT,
    MAX_BOUND,
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_MISS,
    STATUS_REPEAT,
    inspect_alignment,
    run_inspect,
    validate_inspect_payload,
)
from app.main import app
from app.validation import ValidationError

client = TestClient(app)


# ---- 穷举判据 ------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _all_paths(H, R, D):
    """枚举 (0,0)→(H,R) 的匹配/漏纬/重纬路径，带 |i-j|≤D 与各类上限 D。"""
    paths: list[list[str]] = []
    cur: list[tuple[int, int, int, int, list[str]]] = [(0, 0, 0, 0, [])]
    while cur:
        i, j, miss_n, rep_n, steps = cur.pop()
        if i == H and j == R:
            paths.append(steps)
            continue
        if i < H and j < R and abs((i + 1) - (j + 1)) <= D:
            cur.append((i + 1, j + 1, miss_n, rep_n, steps + [EDGE_MATCH]))
        if i < H and miss_n < D and abs((i + 1) - j) <= D:
            cur.append((i + 1, j, miss_n + 1, rep_n, steps + [EDGE_MISS]))
        if j < R and rep_n < D and abs(i - (j + 1)) <= D:
            cur.append((i, j + 1, miss_n, rep_n + 1, steps + [EDGE_REPEAT]))
    return paths


def _brute_inspect(ref, read, D):
    """对全部 (方向, 起点, 路径) 求分层最优，返回与 API 同口径的裁决信息。"""
    H, W = len(ref), len(ref[0])
    R = len(read)
    best = None
    for dir_rank, direction in enumerate(
        (DIRECTION_FORWARD, DIRECTION_REVERSE)
    ):
        for start0 in range(H):
            def rot(k):
                return (start0 + k) % H if direction == DIRECTION_FORWARD else (
                    start0 - k
                ) % H

            for steps in _all_paths(H, R, D):
                i = j = 0
                score = events = 0
                path_slots: list[tuple[int, int]] = []
                for s in steps:
                    if s == EDGE_MATCH:
                        phys = rot(i)
                        score += sum(
                            a != b for a, b in zip(ref[phys], read[j])
                        )
                        # 匹配事件同样参与路径裁决（种类秩 0）。
                        path_slots.append((0, phys + 1))
                        i += 1
                        j += 1
                    elif s == EDGE_MISS:
                        phys = rot(i)
                        score += W
                        events += 1
                        path_slots.append((1, phys + 1))
                        i += 1
                    else:
                        phys = rot((i - 1) % H)
                        score += W + sum(
                            a != b for a, b in zip(ref[phys], read[j])
                        )
                        events += 1
                        path_slots.append((2, phys + 1))
                        j += 1
                path_tuple = tuple(sorted(path_slots))
                key = (score, events, dir_rank, start0, path_tuple)
                if best is None or key < best[0]:
                    best = (key, direction, start0 + 1)
    return best


def _random_matrix(rng, H, W):
    return ["".join(rng.choice("01") for _ in range(W)) for _ in range(H)]


def _perturb(rng, ref, D, W):
    """随机选起点/方向，并随机漏纬、重纬、改错孔，生成回读。"""
    H = len(ref)
    direction = rng.choice((DIRECTION_FORWARD, DIRECTION_REVERSE))
    start0 = rng.randrange(H)
    n_miss = rng.randint(0, min(D, H - 1))
    n_rep = rng.randint(0, D)
    miss_idx = set(rng.sample(range(H), n_miss)) if n_miss else set()
    order = list(range(H))
    if direction == DIRECTION_REVERSE:
        order.reverse()
    read = []
    for k in order:
        phys = (start0 + k) % H if direction == DIRECTION_FORWARD else (
            start0 - k
        ) % H
        if phys in miss_idx:
            continue
        row = list(ref[phys])
        if rng.random() < 0.5:
            c = rng.randrange(W)
            row[c] = "1" if row[c] == "0" else "0"
        read.append("".join(row))
        if n_rep and rng.random() < n_rep / max(1, H):
            rep = list(row)
            if rng.random() < 0.3:
                c = rng.randrange(W)
                rep[c] = "1" if rep[c] == "0" else "0"
            read.append("".join(rep))
            n_rep -= 1
    return read, direction, start0


def test_exhaustive_alignment_matches_bruteforce():
    rng = random.Random(20260915)
    for trial in range(180):
        H = rng.randint(2, 5)
        W = rng.randint(2, 4)
        D = rng.randint(0, min(3, MAX_BOUND))
        ref = _random_matrix(rng, H, W)
        if trial % 3 == 0:
            read, _, _ = _perturb(rng, ref, D, W)
        else:
            # 任意同宽 0/1 回读（行数受 H±D 约束）
            R = rng.randint(max(1, H - D), H + D)
            read = _random_matrix(rng, R, W)
        if not (H - D <= len(read) <= H + D):
            continue
        result = run_inspect(ref, read, D)
        expected = _brute_inspect(ref, read, D)
        assert result.direction == expected[1], (H, W, D, ref, read)
        assert result.start_pick == expected[2], (H, W, D, ref, read)
        assert result.score == expected[0][0], (H, W, D, ref, read)
        assert result.event_count == expected[0][1], (H, W, D, ref, read)
        # 分层排序：错纬事件恰为漏/重，且按 (种类, 物理纬号) 排序。
        kinds = [e["kind"] for e in result.events]
        assert all(k in (STATUS_MISS, STATUS_REPEAT) for k in kinds)
        ordered = tuple(
            (1 if e["kind"] == STATUS_MISS else 2, e["ref_pick"])
            for e in result.events
        )
        assert ordered == tuple(sorted(ordered))


def test_exact_readback_zero_score():
    ref = ["10", "01", "11", "00"]
    r = run_inspect(ref, list(ref), 2)
    assert r.score == 0 and r.event_count == 0
    assert r.direction == DIRECTION_FORWARD and r.start_pick == 1
    assert [list(m) for m in r.mapping] == [[1], [2], [3], [4]]
    assert all(t["status"] == STATUS_MATCH for t in r.timeline)


def test_rotated_forward_start_detected():
    ref = ["10", "01", "11", "00"]
    # 从第 3 纬正向采集：11,00,10,01
    r = run_inspect(ref, ["11", "00", "10", "01"], 2)
    assert r.direction == DIRECTION_FORWARD and r.start_pick == 3
    assert r.score == 0 and r.event_count == 0


def test_reverse_cross_seam_start_detected():
    ref = ["10", "01", "11", "00"]
    # 从第 1 纬反向采集（跨首尾）：10,00,11,01
    r = run_inspect(ref, ["10", "00", "11", "01"], 2)
    assert r.direction == DIRECTION_REVERSE and r.start_pick == 1
    assert r.score == 0 and r.event_count == 0
    # 从第 4 纬反向：00,11,01,10
    r2 = run_inspect(ref, ["00", "11", "01", "10"], 2)
    assert r2.direction == DIRECTION_REVERSE and r2.start_pick == 4
    assert r2.score == 0


def test_missing_pick_event_scores_W():
    ref = ["10", "01", "11", "00"]
    r = run_inspect(ref, ["10", "11", "00"], 2)  # 漏第 2 纬
    assert r.score == 2 and r.event_count == 1
    assert r.miss_count == 1 and r.repeat_count == 0
    miss = [t for t in r.timeline if t["kind"] == STATUS_MISS]
    assert len(miss) == 1 and miss[0]["ref_pick"] == 2
    assert miss[0]["read_row"] is None
    # 基准纬→回读纬映射：漏纬为空，其余连续。
    assert [list(m) for m in r.mapping] == [[1], [], [2], [3]]
    assert [e["kind"] for e in r.events] == [STATUS_MISS]


def test_identical_rows_missing_marked_on_later_pick():
    # 相同纹板行只回读到一纬时，漏纬必须标到靠后的重复纬（第二纬），
    # 而不是第一纬：路径按 匹配<漏纬 排序后，(匹配@1,漏纬@2) 小于
    # (漏纬@1,匹配@2)。
    r = run_inspect(["10", "10"], ["10"], 1)
    assert r.score == 2 and r.event_count == 1
    assert r.miss_count == 1
    assert [e["ref_pick"] for e in r.events] == [2]
    assert [list(m) for m in r.mapping] == [[1], []]
    miss = [t for t in r.timeline if t["kind"] == STATUS_MISS]
    assert len(miss) == 1 and miss[0]["ref_pick"] == 2
    aligned = [t for t in r.timeline if t["kind"] == "aligned"]
    assert [t["ref_pick"] for t in aligned] == [1]


def test_identical_rows_multiple_misses_pushed_late():
    # 三行相同只读到一纬：匹配第 1 纬，漏纬标到第 2、3 纬（而不是 1、3）。
    r = run_inspect(["10", "10", "10"], ["10"], 2)
    assert r.miss_count == 2
    assert [e["ref_pick"] for e in r.events] == [2, 3]
    assert [list(m) for m in r.mapping] == [[1], [], []]


def test_identical_rows_miss_pushed_late_inside_pattern():
    # 相同对出现在尾部：读到 01、10，漏纬应标第 3 纬而非第 2 纬。
    r = run_inspect(["01", "10", "10"], ["01", "10"], 1)
    assert r.miss_count == 1
    assert [e["ref_pick"] for e in r.events] == [3]
    assert [list(m) for m in r.mapping] == [[1], [2], []]


def test_identical_rows_repeat_marked_on_earlier_pick():
    # 相同两纬回读三行时，重纬应标在更靠前的重复纬（第一纬）：
    # (匹配@1,匹配@2,重纬@1) 排序后在重纬槽位上小于 重纬@2。
    r = run_inspect(["10", "10"], ["10", "10", "10"], 1)
    assert r.repeat_count == 1
    assert [e["ref_pick"] for e in r.events] == [1]
    assert [list(m) for m in r.mapping] == [[1, 2], [3]]


def test_repeated_pick_event_and_mapping():
    ref = ["10", "01", "11", "00"]
    r = run_inspect(ref, ["10", "01", "01", "11", "00"], 2)  # 第 2 纬重读
    assert r.score == 2 and r.event_count == 1
    assert r.repeat_count == 1 and r.miss_count == 0
    # 第 2 纬映射到两个回读行（采集序 2 与 3）。
    assert [list(m) for m in r.mapping] == [[1], [2, 3], [4], [5]]
    rep = [t for t in r.timeline if t["kind"] == STATUS_REPEAT]
    assert rep and rep[0]["ref_pick"] == 2 and rep[0]["read_seq"] == 3


def test_hole_mismatch_per_cell():
    ref = ["10", "01", "11", "00"]
    r = run_inspect(ref, ["11", "01", "11", "00"], 2)  # 首纬 1 孔不符
    assert r.event_count == 0
    assert r.score == 1 and r.mismatch_picks == 1 and r.mismatch_cells == 1
    statuses = [t["status"] for t in r.timeline]
    assert statuses == [
        STATUS_MISMATCH,
        STATUS_MATCH,
        STATUS_MATCH,
        STATUS_MATCH,
    ]
    bad = [c for c in r.timeline[0]["cells"] if not c["same"]]
    assert bad == [{"ref": 0, "read": 1, "same": False}]


def test_layered_score_then_events_tiebreak():
    # 构造两种解释：A=2 孔不符（总分 2、事件 0）；B=1 漏纬（总分 W=4、事件 1）。
    # 必须先按总分选 A，即便它有更多不符孔。
    ref = ["0000", "1111", "0101"]
    read = ["0011", "1111", "0101"]  # 首纬 2 孔不同
    r = run_inspect(ref, read, 2)
    assert r.event_count == 0 and r.score == 2
    # 反之 5 孔不符时，漏纬（W=4）总分更低：选漏纬。
    read2 = ["1111", "1111", "0101"]  # 首纬全反 4 孔，仍 ≤ 漏纬 W=4
    r2 = run_inspect(ref, read2, 2)
    assert r2.score == 4
    # 同总分（恰好 4 孔不同）时第二层“事件数少”优先：取 0 事件的全匹配解释。
    assert r2.event_count == 0


def test_direction_forward_preferred_on_tie():
    # 回读关于某行对称，使正/反解释同分同事件数：必须取正向。
    ref = ["10", "10", "01", "01"]
    r = run_inspect(ref, list(ref), 1)
    assert r.direction == DIRECTION_FORWARD
    assert r.start_pick == 1


def test_smaller_start_preferred_on_tie():
    # 全部行相同：任意起点都 0 分，取最小起点 1 且正向。
    ref = ["10", "10", "10"]
    r = run_inspect(ref, ["10", "10", "10"], 1)
    assert r.direction == DIRECTION_FORWARD and r.start_pick == 1


def test_timeline_and_mapping_consistency():
    rng = random.Random(77)
    ref = _random_matrix(rng, 6, 3)
    read, _, _ = _perturb(rng, ref, 2, 3)
    r = run_inspect(ref, read, 2)
    aligned = [t for t in r.timeline if t["kind"] == "aligned"]
    # 每个非漏纬基准纬恰有一条 aligned；回读行在 aligned/repeat 中各出现一次。
    assert len(aligned) == 6 - r.miss_count
    used_seq = sorted(
        t["read_seq"] for t in r.timeline if t["read_seq"] is not None
    )
    assert used_seq == list(range(1, len(read) + 1))
    # 总分可复算：事件*W + 逐格差异（含重纬复读行）。
    diff_cells = sum(
        sum(1 for c in t["cells"] if not c["same"]) for t in r.timeline
    )
    assert r.score == r.event_count * 3 + diff_cells
    # mapping 覆盖：漏纬为空，其余与时间线一致。
    map_flat = sorted(s for m in r.mapping for s in m)
    aligned_or_rep = sorted(
        t["read_seq"]
        for t in r.timeline
        if t["kind"] in ("aligned", STATUS_REPEAT)
    )
    assert map_flat == aligned_or_rep


# ---- 校验：整次拒绝 ------------------------------------------------------

def inspect_payload(**ov):
    p = {
        "matrix": ["10", "01", "11"],
        "readback": ["10", "01", "11"],
        "max_misses": 2,
    }
    p.update(ov)
    return p


@pytest.mark.parametrize(
    "payload",
    [
        inspect_payload(readback=["20", "01", "11"]),          # 非法字符
        inspect_payload(readback=["1", "01", "11"]),           # 宽度不一致
        inspect_payload(readback=["10", "010", "11"]),         # 回读行内不等宽
        inspect_payload(readback=["10", "01", "1?"]),          # 回读含 ?
        inspect_payload(max_misses=21),                        # 上限越界
        inspect_payload(max_misses=-1),
        inspect_payload(max_misses="2"),                       # 类型错误
        inspect_payload(readback=["10"], max_misses=1),  # 行数 1 < H-D=2
        inspect_payload(readback=["10", "01"], max_misses=0),  # D=0 时行数须恰为 H
        inspect_payload(readback=["10", "01", "11", "10", "01", "11"], max_misses=2),  # H+3 > H+D
        inspect_payload(matrix=["10", "01", "1"]),             # 基准不等宽
        inspect_payload(matrix=["10", "01"], max_misses=0),  # H=2,D=0 但回读 3 行
        inspect_payload(readback=[]),                          # 空回读
        inspect_payload(readback="10,01,11"),                  # 非数组
        inspect_payload(readback=["10", "01", ""]),            # 夹空行
        {},                                                    # 缺字段
    ],
)
def test_invalid_inspect_rejected(payload):
    with pytest.raises(ValidationError):
        validate_inspect_payload(payload)


def test_bound_zero_requires_exact_length():
    # D=0：行数必须恰为 H。
    with pytest.raises(ValidationError):
        validate_inspect_payload(
            inspect_payload(readback=["10", "01"], max_misses=0)
        )
    with pytest.raises(ValidationError):
        validate_inspect_payload(
            inspect_payload(
                readback=["10", "01", "11", "10"], max_misses=0
            )
        )
    validate_inspect_payload(inspect_payload(max_misses=0))


def test_bound_at_limits_accepted():
    base = ["10", "01", "11"]
    # H=3, D=2：行数 1～5 均可
    validate_inspect_payload(
        inspect_payload(readback=["10"])
    )
    validate_inspect_payload(
        inspect_payload(
            readback=["10", "01", "11", "10", "01"]
        )
    )


# ---- HTTP 接口 -----------------------------------------------------------

def test_api_inspect_success():
    r = client.post(
        "/api/inspect",
        json=inspect_payload(
            readback=["11", "01", "11"]
        ),  # 首纬 1 孔不符
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["direction"] == "forward"
    assert body["start_pick"] == 1
    assert body["score"] == 1 and body["event_count"] == 0
    assert body["mismatch_cells"] == 1
    assert body["mapping"] == [[1], [2], [3]]
    assert body["height"] == 3 and body["width"] == 2
    kinds = {t["status"] for t in body["timeline"]}
    assert STATUS_MISMATCH in kinds and STATUS_MATCH in kinds
    for t in body["timeline"]:
        if t["kind"] == "aligned":
            assert len(t["cells"]) == 2
            assert set(t) == {
                "kind", "status", "ref_pick", "read_seq",
                "ref_row", "read_row", "cells", "mismatch_count",
            }


def test_api_inspect_reverse_cross_seam():
    r = client.post(
        "/api/inspect",
        json={
            "matrix": ["10", "01", "11", "00"],
            "readback": ["10", "00", "11", "01"],
            "max_misses": 2,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["direction"] == "reverse"
    assert body["start_pick"] == 1
    assert body["score"] == 0


def test_api_inspect_rejected_keeps_http_contract():
    r = client.post(
        "/api/inspect",
        json=inspect_payload(readback=["20", "01", "11"]),
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert any("非法字符" in e for e in body["errors"])
    assert "timeline" not in body


def test_api_inspect_row_count_out_of_bound():
    r = client.post(
        "/api/inspect",
        json=inspect_payload(
            max_misses=1, readback=["10", "01", "11", "10", "01"]
        ),
    )
    assert r.status_code == 400
    assert any("超出" in e for e in r.json()["errors"])


def test_api_inspect_bad_json():
    r = client.post(
        "/api/inspect",
        content="{not json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json()["ok"] is False
