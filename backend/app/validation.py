"""输入校验与逐格差异分类。

整次拒绝原则：高度、宽度、K、L 或矩阵中任一项不合法，都收集全部错误后
一次性抛出 :class:`ValidationError`，由 API 返回 400，前端据此清除旧解。
"""

from __future__ import annotations

MIN_H, MAX_H = 2, 200
MIN_W, MAX_W = 2, 10
ALLOWED_CHARS = frozenset("01?")


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("；".join(errors))
        self.errors = errors


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_request(
    payload: object,
) -> tuple[int, int, int, int, list[list[str]]]:
    errors: list[str] = []

    if not isinstance(payload, dict):
        raise ValidationError(["请求体必须是 JSON 对象"])

    height = payload.get("height")
    width = payload.get("width")
    picks = payload.get("picks")
    max_float = payload.get("max_float")
    rows = payload.get("rows")

    h_ok = _is_int(height) and MIN_H <= height <= MAX_H
    w_ok = _is_int(width) and MIN_W <= width <= MAX_W
    if not h_ok:
        errors.append(f"高度必须是 {MIN_H}～{MAX_H} 的整数")
    if not w_ok:
        errors.append(f"宽度必须是 {MIN_W}～{MAX_W} 的整数")

    # 逐行解析：非法类型 / 非法字符都记录，但每行仍占位，保证行数检查准确。
    grid: list[list[str] | None] = []
    if not isinstance(rows, list) or not rows:
        errors.append("矩阵必须是非空的字符串数组（每行一个字符串）")
        row_strings: list[str] = []
    else:
        row_strings = []
        for idx, row in enumerate(rows):
            if not isinstance(row, str):
                errors.append(f"第 {idx + 1} 行必须是字符串")
                grid.append(None)
                continue
            row_strings.append(row)
            chars = list(row)
            grid.append(chars)
            bad = [c for c in chars if c not in ALLOWED_CHARS]
            if bad:
                errors.append(
                    f"第 {idx + 1} 行含非法字符 "
                    f"{''.join(sorted(set(bad)))}（仅允许 0、1、?）"
                )

    if h_ok and isinstance(rows, list) and len(grid) != height:
        errors.append(f"矩阵行数 {len(grid)} 与高度 {height} 不一致")

    if w_ok and row_strings:
        lengths = {len(r) for r in row_strings}
        if len(lengths) > 1:
            errors.append("矩阵各行长度不等（必须为等长矩阵）")
        elif len(lengths) == 1 and next(iter(lengths)) != width:
            errors.append(
                f"行宽 {next(iter(lengths))} 与宽度 {width} 不一致（必须为等长矩阵）"
            )

    if not _is_int(picks) or not (w_ok and 0 <= picks <= width):
        errors.append(
            f"每纬抬综数 K 必须是 0～{width if w_ok else MAX_W} 的整数"
        )
    if not _is_int(max_float) or not (h_ok and 1 <= max_float <= height):
        errors.append(
            f"最大循环浮长 L 必须是 1～{height if h_ok else MAX_H} 的整数"
        )

    if errors:
        raise ValidationError(errors)

    # 到达此处时所有行必为合法字符串（grid 中无 None）。
    return height, width, picks, max_float, grid  # type: ignore[return-value]


# ---- 逐格差异分类 -------------------------------------------------------

# 原孔 original_hole：输入 1，修复后仍为 1
# 补孔 added_hole：   输入 0，修复后为 1（补上丢失的孔，计一次改动）
# 改孔 removed_hole： 输入 1，修复后改为 0（纠正误孔，计一次改动）
# 保留空格 kept_blank：输入 0，修复后仍为 0
# 缺失定孔 unknown_hole：输入 ? ，修复后为 1（不计改动）
# 缺失定空 unknown_blank：输入 ? ，修复后为 0（不计改动）
def classify_cell(input_char: str, output_bit: int) -> str:
    if input_char == "1":
        return "original_hole" if output_bit == 1 else "removed_hole"
    if input_char == "0":
        return "added_hole" if output_bit == 1 else "kept_blank"
    return "unknown_hole" if output_bit == 1 else "unknown_blank"
