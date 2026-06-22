#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Configure Claude Code to use DeepSeek Anthropic API
# For Windows + Git Bash
# ============================================================

CLAUDE_DIR="$HOME/.claude"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"

DEEPSEEK_BASE_URL="https://api.deepseek.com/anthropic"

# 官方 Claude Code 集成推荐：
# 主模型：deepseek-v4-pro[1m]
# 轻量/子代理模型：deepseek-v4-flash
DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-v4-pro[1m]}"
DEEPSEEK_FAST_MODEL="${DEEPSEEK_FAST_MODEL:-deepseek-v4-flash}"

mkdir -p "$CLAUDE_DIR"

echo "请输入 DeepSeek API Key，输入时不会显示："
read -r -s DEEPSEEK_API_KEY
echo

if [ -z "$DEEPSEEK_API_KEY" ]; then
  echo "[ERROR] DeepSeek API Key 不能为空"
  exit 1
fi

if [ -f "$SETTINGS_FILE" ]; then
  BACKUP_FILE="${SETTINGS_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
  cp "$SETTINGS_FILE" "$BACKUP_FILE"
  echo "[OK] 已备份旧配置到: $BACKUP_FILE"
fi

cat > "$SETTINGS_FILE" <<EOF
{
  "\$schema": "https://json.schemastore.org/claude-code-settings.json",
  "env": {
    "ANTHROPIC_BASE_URL": "$DEEPSEEK_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN": "$DEEPSEEK_API_KEY",
    "ANTHROPIC_MODEL": "$DEEPSEEK_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "$DEEPSEEK_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "$DEEPSEEK_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "$DEEPSEEK_FAST_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL": "$DEEPSEEK_FAST_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL": "$DEEPSEEK_FAST_MODEL",
    "CLAUDE_CODE_EFFORT_LEVEL": "max",
    "API_TIMEOUT_MS": "1200000",
    "BASH_DEFAULT_TIMEOUT_MS": "1200000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  }
}
EOF

echo "[OK] 已写入 Claude Code 全局 settings.json:"
echo "     $SETTINGS_FILE"

# 同步写入 Windows 用户级环境变量。
# 这样从 Windows Terminal / PowerShell / CMD 直接运行 claude 时也会走 DeepSeek。
export DEEPSEEK_API_KEY
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command '
$vars = @{
  "ANTHROPIC_BASE_URL" = "https://api.deepseek.com/anthropic"
  "ANTHROPIC_AUTH_TOKEN" = $env:DEEPSEEK_API_KEY
  "ANTHROPIC_MODEL" = "deepseek-v4-pro[1m]"
  "ANTHROPIC_DEFAULT_OPUS_MODEL" = "deepseek-v4-pro[1m]"
  "ANTHROPIC_DEFAULT_SONNET_MODEL" = "deepseek-v4-pro[1m]"
  "ANTHROPIC_DEFAULT_HAIKU_MODEL" = "deepseek-v4-flash"
  "ANTHROPIC_SMALL_FAST_MODEL" = "deepseek-v4-flash"
  "CLAUDE_CODE_SUBAGENT_MODEL" = "deepseek-v4-flash"
  "CLAUDE_CODE_EFFORT_LEVEL" = "max"
  "API_TIMEOUT_MS" = "1200000"
  "BASH_DEFAULT_TIMEOUT_MS" = "1200000"
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" = "1"
}

foreach ($k in $vars.Keys) {
  [Environment]::SetEnvironmentVariable($k, [string]$vars[$k], "User")
}

# 避免旧的 Anthropic API Key 干扰第三方 Anthropic-compatible 路由
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", $null, "User")

Write-Host "[OK] Windows 用户级环境变量已写入 DeepSeek 配置"
'

echo
echo "[CHECK] 当前 settings.json，已隐藏 token："
sed -E 's/"ANTHROPIC_AUTH_TOKEN": ".*"/"ANTHROPIC_AUTH_TOKEN": "***hidden***"/' "$SETTINGS_FILE"

echo
echo "[DONE] 配置完成。"
echo "请关闭所有 Git Bash / PowerShell / Windows Terminal 窗口，然后重新打开终端。"
echo
echo "进入项目目录后运行："
echo "  claude"
echo
echo "如果还想跳过权限确认，可运行："
echo "  claude --dangerously-skip-permission"
