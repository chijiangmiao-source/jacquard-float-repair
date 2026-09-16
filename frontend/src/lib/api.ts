import type {
  ErrorResponse,
  InspectInput,
  InspectResponse,
  RepairInput,
  RepairResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  infeasible: boolean;
  constructor(messages: string[], infeasible: boolean) {
    super(messages.join("；"));
    this.infeasible = infeasible;
  }
}

export async function repairMatrix(
  input: RepairInput,
): Promise<RepairResponse> {
  // 后端使用 snake_case，边界处做一次字段名转换。
  const payload = {
    height: input.height,
    width: input.width,
    picks: input.picks,
    max_float: input.maxFloat,
    rows: input.rows,
  };
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/api/repair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError(["无法连接修复服务，请检查 API 是否可用"], false);
  }

  let body: ErrorResponse | RepairResponse;
  try {
    body = (await resp.json()) as ErrorResponse | RepairResponse;
  } catch {
    throw new ApiError([`服务返回异常（HTTP ${resp.status}）`], false);
  }

  if (!resp.ok || !body.ok) {
    const err = body as ErrorResponse;
    throw new ApiError(
      err.errors?.length ? err.errors : ["未知服务错误"],
      err.infeasible === true,
    );
  }
  return body as RepairResponse;
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError(["无法连接核验服务，请检查 API 是否可用"], false);
  }

  let body: ErrorResponse | T;
  try {
    body = (await resp.json()) as ErrorResponse | T;
  } catch {
    throw new ApiError([`服务返回异常（HTTP ${resp.status}）`], false);
  }

  if (!resp.ok || !(body as { ok?: boolean }).ok) {
    const err = body as ErrorResponse;
    throw new ApiError(
      err.errors?.length ? err.errors : ["未知服务错误"],
      err.infeasible === true,
    );
  }
  return body as T;
}

export async function inspectMatrix(
  input: InspectInput,
): Promise<InspectResponse> {
  // 试打核验：随附已批准修复矩阵与设备回读，后端只做对齐、不重新求解。
  return postJson<InspectResponse>("/api/inspect", {
    matrix: input.matrix,
    readback: input.readback,
    max_misses: input.maxMisses,
  });
}
