#!/usr/bin/env bash

set -euo pipefail



# Claude Code global settings path under Git Bash:

# /c/Users/<username>/.claude/settings.json

CLAUDE_DIR="$HOME/.claude"

SETTINGS_FILE="$CLAUDE_DIR/settings.json"



# 改成你的 Kimi API Key

KIMI_API_KEY="sk-kimi-mG9XBDLUsctqxEGGRnGGU7jxMvzszlfPhnDgtN4J1UdAaghqhsZ4YlLJmP8xn8hA"



KIMI_BASE_URL="https://api.kimi.com/coding/"

KIMI_MODEL="kimi-k2.6"



mkdir -p "$CLAUDE_DIR"



if [ -f "$SETTINGS_FILE" ]; then

  BACKUP_FILE="${SETTINGS_FILE}.bak.$(date +%Y%m%d_%H%M%S)"

  cp "$SETTINGS_FILE" "$BACKUP_FILE"

  echo "[OK] 已备份旧配置到: $BACKUP_FILE"

fi



cat > "$SETTINGS_FILE" <<EOF

{

  "\$schema": "https://json.schemastore.org/claude-code-settings.json",

  "env": {

    "ANTHROPIC_BASE_URL": "$KIMI_BASE_URL",

    "ANTHROPIC_AUTH_TOKEN": "$KIMI_API_KEY",

    "ANTHROPIC_MODEL": "$KIMI_MODEL",

    "ANTHROPIC_SMALL_FAST_MODEL": "$KIMI_MODEL",

    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"

  }

}

EOF



echo

echo "[OK] Claude Code settings.json 已写入 Kimi 配置"

echo "[PATH] $SETTINGS_FILE"

echo

echo "当前内容如下："

cat "$SETTINGS_FILE"

echo

echo "接下来重新打开 Git Bash，然后运行："

echo 'claude --teammate-mode in-process --dangerously-skip-permission
s'