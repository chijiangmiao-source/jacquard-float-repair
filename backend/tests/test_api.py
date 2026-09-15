"""校验整次拒绝与 HTTP 接口测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
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
