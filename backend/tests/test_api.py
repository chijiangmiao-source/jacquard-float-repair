"""校验整次拒绝与 HTTP 接口测试。"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app
from app.solver import RepairResult
from app.validation import ValidationError, validate_request

client = TestClient(app)


def base_payload(**overrides):
    payload = {
        "height": 3,
        "width": 2,
        "picks": 1,
        "max_float": 3,
        "rows": ["01", "10", "01"],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        base_payload(rows=["02", "10", "01"]),          # 非法字符
        base_payload(rows=["0", "10", "01"]),           # 非等长 / 与宽度不符
        base_payload(rows=["010", "10", "01"]),         # 行宽与 W 不符
        base_payload(height=2),                          # 行数与高度不符
        base_payload(height=1),                          # 高度越界
        base_payload(height=201),
        base_payload(width=1),                           # 宽度越界
        base_payload(width=11),
        base_payload(picks=3),                           # K 越界（W=2）
        base_payload(picks=-1),
        base_payload(max_float=4),                       # L 越界（H=3）
        base_payload(max_float=0),
        base_payload(height="3"),                        # 类型错误
        base_payload(rows="01,10,01"),
        base_payload(rows=["01", 10, "01"]),             # 行非字符串
        base_payload(rows=[["01"], ["10"], ["01"]]),     # 行非字符串
        base_payload(rows=["01", "", "10"]),             # 夹空行
        base_payload(rows=["01", "1 0", "10"]),          # 夹空格
        base_payload(rows=["01", "10", "10\n"]),         # 行内换行符
        {},                                              # 缺字段
    ],
)
def test_invalid_requests_rejected(payload):
    with pytest.raises(ValidationError):
        validate_request(payload)


def test_api_rejects_illegal_character():
    r = client.post("/api/repair", json=base_payload(rows=["02", "10", "01"]))
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert any("非法字符" in e for e in body["errors"])
    assert "matrix" not in body


def test_api_rejects_ragged_rows():
    r = client.post("/api/repair", json=base_payload(width=3, rows=["010", "10", "01?"]))
    assert r.status_code == 400
    assert any("不等" in e for e in r.json()["errors"])


def test_api_infeasible_returns_422():
    # 奇环 L=1 无解。
    payload = base_payload(
        height=3, width=2, picks=1, max_float=1, rows=["??", "??", "??"]
    )
    r = client.post("/api/repair", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False and body["infeasible"] is True


def test_api_success_payload_and_diff():
    payload = base_payload(
        height=2,
        width=2,
        picks=1,
        max_float=2,
        rows=["11", "00"],
    )
    r = client.post("/api/repair", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # 首行删 1 个误孔、次行补 1 个丢孔，共 2 处改动。
    assert body["changes"] == 2
    # 每纬恰有 1 个 1
    assert all(sum(row) == 1 for row in body["matrix"])
    kinds = {c["kind"] for row in body["diff"] for c in row}
    assert {"original_hole", "kept_blank", "removed_hole", "added_hole"} <= kinds
    for row in body["diff"]:
        for cell in row:
            assert set(cell) == {"input", "output", "kind", "counts_as_change"}


def test_api_change_classification():
    # 00/00, K=1：每行需补 1 个孔（added_hole）。
    payload = base_payload(
        height=2, width=2, picks=1, max_float=2, rows=["00", "00"]
    )
    body = client.post("/api/repair", json=payload).json()
    assert body["changes"] == 2
    changed = [
        c
        for row in body["diff"]
        for c in row
        if c["counts_as_change"]
    ]
    assert len(changed) == 2
    assert all(c["kind"] == "added_hole" for c in changed)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_slow_solve_does_not_block_event_loop(monkeypatch):
    # 打桩：复杂纹板“求解”在事件循环上直接 sleep 2 秒（模拟 CPU 密集同步调用）。
    entered = threading.Event()

    def slow_repair(grid, H, W, K, L):
        entered.set()
        time.sleep(2.0)
        return RepairResult(
            matrix=tuple(tuple(0 for _ in range(W)) for _ in range(H)),
            changes=0,
            solve_seconds=2.0,
        )

    monkeypatch.setattr(main_module, "repair", slow_repair)
    payload = base_payload(
        height=2, width=2, picks=0, max_float=2, rows=["00", "00"]
    )
    bad_payload = base_payload(rows=["12", "10", "01"])

    import asyncio

    import httpx

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            slow_task = asyncio.ensure_future(ac.post("/api/repair", json=payload))
            # 等到慢求解确实开始（在线程池中阻塞期间，事件循环仍须可调度）
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set(), "慢求解未能开始"
            # 阻塞实现下慢请求会在事件循环上空转到底、此刻已完成；
            # 正确实现中它仍在线程池里运行。
            assert not slow_task.done(), "慢请求未与事件循环并发，疑似同步阻塞"
            t_entered = time.perf_counter()

            # 求解仍在进行：健康检查必须在事件循环上即时响应。
            health_resp = await ac.get("/health")
            health_latency = time.perf_counter() - t_entered
            assert health_resp.status_code == 200
            assert health_latency < 0.5, f"健康检查被阻塞：{health_latency:.2f}s"

            # 另一个用户的非法请求也应即时 400，而不是排在慢求解之后。
            t0 = time.perf_counter()
            bad_resp = await ac.post("/api/repair", json=bad_payload)
            bad_latency = time.perf_counter() - t0
            assert bad_resp.status_code == 400
            assert bad_latency < 0.5, f"非法请求被阻塞：{bad_latency:.2f}s"

            slow_resp = await slow_task
            assert slow_resp.status_code == 200

    asyncio.run(scenario())


def test_two_solves_run_concurrently(monkeypatch):
    # 同一事件循环内并发两个 1.2s 求解：串行需 ≥2.4s，线程池并行应明显更短。
    gate = threading.Event()

    def slow_repair(grid, H, W, K, L):
        gate.wait(timeout=3.0)
        time.sleep(1.2)
        return RepairResult(
            matrix=tuple(tuple(0 for _ in range(W)) for _ in range(H)),
            changes=0,
            solve_seconds=1.2,
        )

    monkeypatch.setattr(main_module, "repair", slow_repair)
    payload = base_payload(
        height=2, width=2, picks=0, max_float=2, rows=["00", "00"]
    )

    import asyncio

    import httpx

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            t0 = time.perf_counter()
            tasks = [
                asyncio.ensure_future(ac.post("/api/repair", json=payload))
                for _ in range(2)
            ]
            await asyncio.sleep(0.5)  # 让两个请求都进入线程池
            gate.set()
            responses = await asyncio.gather(*tasks)
            return time.perf_counter() - t0, [r.status_code for r in responses]

    elapsed, statuses = asyncio.run(scenario())
    assert statuses == [200, 200]
    assert elapsed < 2.0, f"两个求解请求疑似串行：{elapsed:.2f}s"
