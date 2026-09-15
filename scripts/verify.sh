#!/usr/bin/env bash
# 一次性验收：后端 pytest（含小规模穷举判据）→ 前端 Vitest →
# 等待 compose 中的 api/web 就绪 → 对真实服务跑 Playwright E2E。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==================== [1/4] 后端 pytest（含穷举判据） ===================="
cd backend
python -m pytest -q
cd "$ROOT"

echo "==================== [2/4] 前端 Vitest ===================="
cd frontend
npm run test
cd "$ROOT"

echo "==================== [3/4] 等待 api / web 服务就绪 ===================="
wait_url() {
  local url="$1" n=0
  until curl -fsS "$url" >/dev/null 2>&1; do
    n=$((n + 1))
    if [ "$n" -ge 60 ]; then
      echo "等待 $url 超时" >&2
      exit 1
    fi
    sleep 2
  done
  echo "$url 就绪"
}
wait_url "${API_HEALTH_URL:-http://api:8000/health}"
wait_url "${WEB_URL:-http://web/}"

echo "==================== [4/4] Playwright E2E（真实 api + web） ===================="
cd frontend
E2E_BASE_URL="${WEB_URL:-http://web}" npx playwright test
cd "$ROOT"

echo ""
echo "✅ 验收通过：pytest / Vitest / Playwright 全部成功。"
