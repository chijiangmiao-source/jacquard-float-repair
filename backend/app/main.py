"""FastAPI 应用：纹板修复接口与健康检查。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .solver import InfeasibleError, repair
from .inspect import run_inspect, validate_inspect_payload
from .validation import classify_cell, validate_request, ValidationError

app = FastAPI(title="提花纹板修复器", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    # 显式 async：直接在事件循环上响应，不占用求解线程池，
    # 因而即使有复杂纹板正在求解，健康检查仍即时返回。
    return {"status": "ok"}


@app.post("/api/repair")
async def repair_matrix(request: Request) -> JSONResponse:
    # 接收原始 JSON，所有字段校验（含类型、非法字符、非等长行）统一由
    # validate_request 一次性完成；任一不合法都整次拒绝。
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "errors": ["请求体必须是合法 JSON"]},
        )

    try:
        H, W, K, L, grid = validate_request(payload)
    except ValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "errors": exc.errors},
        )

    # CP-SAT 求解是 CPU 密集的同步调用，放入线程池执行，避免阻塞事件循环：
    # 求解期间 /health 与其他用户的请求仍可正常响应。
    return await run_in_threadpool(_solve_and_render, grid, H, W, K, L)


def _solve_and_render(grid, H, W, K, L) -> JSONResponse:
    try:
        result = repair(grid, H, W, K, L)
    except InfeasibleError as exc:
        # 不可修复是业务结果而非输入错误：422，前端清除旧解并明确提示。
        return JSONResponse(
            status_code=422,
            content={"ok": False, "infeasible": True, "errors": [str(exc)]},
        )
    except RuntimeError as exc:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "errors": [f"求解失败：{exc}"]},
        )

    matrix = [list(row) for row in result.matrix]
    diff: list[list[dict]] = []
    for i in range(H):
        diff_row: list[dict] = []
        for j in range(W):
            kind = classify_cell(grid[i][j], result.matrix[i][j])
            diff_row.append(
                {
                    "input": grid[i][j],
                    "output": result.matrix[i][j],
                    "kind": kind,
                    "counts_as_change": kind in ("added_hole", "removed_hole"),
                }
            )
        diff.append(diff_row)

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "height": H,
            "width": W,
            "picks": K,
            "max_float": L,
            "matrix": matrix,
            "diff": diff,
            "changes": result.changes,
            "solve_seconds": round(result.solve_seconds, 4),
        },
    )


@app.post("/api/inspect")
async def inspect_matrix(request: Request) -> JSONResponse:
    # 试打核验：以已批准的修复矩阵（请求内随附）为基准，对设备回读矩阵做
    # 有界环形序列对齐。本接口不重新求解、不改写纹板；非法输入只拒绝本次
    # 核验（HTTP 400），由前端保留现有修复结果。
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "errors": ["请求体必须是合法 JSON"]},
        )

    try:
        ref_rows, read_rows, bound = validate_inspect_payload(payload)
    except ValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "errors": exc.errors},
        )

    return await run_in_threadpool(_inspect_and_render, ref_rows, read_rows, bound)


def _inspect_and_render(ref_rows, read_rows, bound) -> JSONResponse:
    try:
        result = run_inspect(ref_rows, read_rows, bound)
    except RuntimeError as exc:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "errors": [f"对齐失败：{exc}"]},
        )

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "height": len(ref_rows),
            "width": len(ref_rows[0]),
            "readback_rows": len(read_rows),
            "max_misses": bound,
            "direction": result.direction,
            "start_pick": result.start_pick,
            "score": result.score,
            "event_count": result.event_count,
            "miss_count": result.miss_count,
            "repeat_count": result.repeat_count,
            "mismatch_picks": result.mismatch_picks,
            "mismatch_cells": result.mismatch_cells,
            "mapping": [list(m) for m in result.mapping],
            "events": list(result.events),
            "timeline": list(result.timeline),
        },
    )
