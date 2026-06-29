#!/usr/bin/env bash
# ============================================================================
# SoulDance — Pre-build Cloudflare Tunnel 自动检查与更新
#
# 编译前运行，确保：
#   1. 后端服务在 127.0.0.1:8000 运行
#   2. Cloudflare tunnel 已建立且可访问
#   3. AppConfig.kt 中的 URL 与实际 tunnel 一致
#
# 当服务已在运行时，耗时 < 1s，不影响日常编译体验。
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPCONFIG="$REPO_ROOT/client/app/src/main/java/com/example/shopguideagent/config/AppConfig.kt"
BACKEND_URL="http://127.0.0.1:8000"
CLOUDFLARED_LOG="/tmp/cloudflared_souldance.log"
START_BACKEND_SCRIPT="$REPO_ROOT/server/scripts/start_backend.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[tunnel]${NC} $*" >&2; }
log_warn()  { echo -e "${YELLOW}[tunnel]${NC} $*" >&2; }
log_error() { echo -e "${RED}[tunnel]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Phase 1 — 确保后端运行
# ---------------------------------------------------------------------------
ensure_backend() {
    if curl -sS --connect-timeout 3 "$BACKEND_URL/health" > /dev/null 2>&1; then
        log_info "后端健康 ✓ (127.0.0.1:8000)"
        return 0
    fi

    log_warn "后端未响应，正在启动..."
    cd "$REPO_ROOT"
    bash "$START_BACKEND_SCRIPT" > /tmp/backend_souldance.log 2>&1 &
    local be_pid=$!

    local waited=0
    while [ $waited -lt 60 ]; do
        sleep 2
        waited=$((waited + 2))
        if curl -sS --connect-timeout 2 "$BACKEND_URL/health" > /dev/null 2>&1; then
            log_info "后端已启动 (耗时 ${waited}s)"
            return 0
        fi
        # 检查进程是否还活着
        if ! kill -0 "$be_pid" 2>/dev/null; then
            log_error "后端进程意外退出，查看日志: /tmp/backend_souldance.log"
            tail -30 /tmp/backend_souldance.log
            return 1
        fi
    done
    log_error "后端启动超时 (60s)"
    return 1
}

# ---------------------------------------------------------------------------
# Phase 2 — 从 AppConfig 读取当前 URL
# ---------------------------------------------------------------------------
get_appconfig_hostname() {
    grep -E '^\s*const val BASE_HTTP_URL' "$APPCONFIG" 2>/dev/null \
        | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' \
        | sed 's|https://||' \
        | head -1
}

# ---------------------------------------------------------------------------
# Phase 3 — 检查 tunnel 是否可访问
# ---------------------------------------------------------------------------
check_tunnel_health() {
    local hostname="$1"
    curl -sS --connect-timeout 5 --max-time 8 "https://${hostname}/health" > /dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Phase 4 — 启动/重启 Cloudflare tunnel
# ---------------------------------------------------------------------------
start_tunnel() {
    # 停掉旧 cloudflared（仅针对端口 8000 的）
    local old_pids
    old_pids=$(pgrep -f "cloudflared.*(tunnel|url).*8000" 2>/dev/null || true)
    if [ -n "$old_pids" ]; then
        log_info "停掉旧的 cloudflared 进程: $old_pids"
        kill $old_pids 2>/dev/null || true
        sleep 2
    fi

    log_info "启动 Cloudflare tunnel → $BACKEND_URL ..."
    cd "$REPO_ROOT"
    cloudflared tunnel --url "$BACKEND_URL" > "$CLOUDFLARED_LOG" 2>&1 &
    local cpid=$!

    local new_url=""
    local waited=0
    while [ $waited -lt 20 ]; do
        sleep 1
        waited=$((waited + 1))
        new_url=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$CLOUDFLARED_LOG" 2>/dev/null | tail -1)
        if [ -n "$new_url" ]; then
            log_info "Tunnel URL: $new_url"
            echo "$new_url"
            return 0
        fi
        if ! kill -0 "$cpid" 2>/dev/null; then
            log_error "cloudflared 意外退出，日志:"
            tail -20 "$CLOUDFLARED_LOG"
            return 1
        fi
    done
    log_error "Tunnel 启动超时 (20s)"
    return 1
}

# ---------------------------------------------------------------------------
# Phase 5 — 更新 AppConfig.kt
# ---------------------------------------------------------------------------
update_appconfig() {
    local old_hostname="$1"
    local new_hostname="$2"

    if [ "$old_hostname" = "$new_hostname" ]; then
        log_info "Tunnel hostname 未变: $new_hostname"
        return 0
    fi

    log_info "更新 AppConfig.kt: $old_hostname → $new_hostname"
    sed -i "/^\s*const val/ s|$old_hostname|$new_hostname|g" "$APPCONFIG"
    log_info "AppConfig.kt 已更新"
}

# ===========================================================================
# Main
# ===========================================================================
echo "════════════════════════════════════════════"
echo " SoulDance — 编译前 Tunnel 检查"
echo "════════════════════════════════════════════"

# 1. 确保后端运行
ensure_backend || exit 1

# 2. 读取 AppConfig 中当前的 hostname
current_hostname=$(get_appconfig_hostname)

if [ -z "$current_hostname" ]; then
    log_error "无法从 AppConfig.kt 解析当前 tunnel URL"
    exit 1
fi
log_info "AppConfig hostname: $current_hostname"

# 3. 快速健康检查
if check_tunnel_health "$current_hostname"; then
    log_info "Tunnel 健康 ✓"
    echo "OK: $current_hostname"
    exit 0
fi

# 4. Tunnel 不可用 → 重启
log_warn "Tunnel $current_hostname 不可达，正在重建..."
new_url=$(start_tunnel) || exit 1

new_hostname=$(echo "$new_url" | sed 's|https://||')

# 5. 更新配置
update_appconfig "$current_hostname" "$new_hostname"

# 6. 最终验证
sleep 3
if check_tunnel_health "$new_hostname"; then
    log_info "新 tunnel 验证通过 ✓"
    echo "UPDATED: $new_hostname"
    exit 0
fi

log_error "新 tunnel 仍不可达，请手动检查"
exit 1
