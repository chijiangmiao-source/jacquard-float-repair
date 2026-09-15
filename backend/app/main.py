"""FastAPI 应用：纹板修复接口与健康检查。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .solver import InfeasibleError, repair
from .validation import classify_cell, validate_request, ValidationError

app = FastAPI(title="提花纹板修复器", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/repair")
async def repair_matrix(request: Request) -> dict:
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

    return {
        "ok": True,
        "height": H,
        "width": W,
        "picks": K,
        "max_float": L,
        "matrix": matrix,
        "diff": diff,
        "changes": result.changes,
        "solve_seconds": round(result.solve_seconds, 4),
    }
