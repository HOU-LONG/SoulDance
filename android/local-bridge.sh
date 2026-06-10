#!/usr/bin/env bash
# ==========================================================
# local-bridge.sh — 在本地电脑上运行，把手机桥接到远程服务器
# ==========================================================
# 用法: ./local-bridge.sh <远程服务器IP> [远程端口] [本地端口]
# 示例: ./local-bridge.sh 192.168.1.100
#
# 前提:
#   1. 手机通过 USB 连接本地电脑
#   2. 本地电脑已安装 adb
#   3. 本地电脑能通过网络访问远程服务器

set -e

# ========== 运行环境检测 ==========
if [ -n "${SSH_CONNECTION:-}" ] || [ -n "${SSH_CLIENT:-}" ] || [ -n "${SSH_TTY:-}" ]; then
    echo "⚠️  警告：检测到当前处于 SSH 远程会话中。"
    echo ""
    echo "    local-bridge.sh 应该在「本地电脑」上运行，而不是远程服务器。"
    echo "    因为手机 USB 只能连接到本地电脑，adb 需要在本地电脑上操作。"
    echo ""
    echo "    如果在本地电脑运行仍看到此提示，请用以下方式强制运行："
    echo "      SSH_CONNECTION='' ./local-bridge.sh <服务器IP>"
    echo ""
    exit 1
fi
# =================================

SERVER_HOST="${1:-}"
SERVER_PORT="${2:-8000}"
LOCAL_PORT="${3:-8000}"

if [ -z "$SERVER_HOST" ]; then
    echo "❌ 请指定远程服务器 IP 或域名"
    echo "用法: ./local-bridge.sh <远程服务器IP> [远程端口] [本地端口]"
    echo "示例: ./local-bridge.sh 192.168.1.100"
    exit 1
fi

echo ">>> 检查 adb..."
if ! command -v adb &>/dev/null; then
    echo "❌ 找不到 adb，请先安装 Android SDK Platform Tools"
    exit 1
fi

echo ">>> 检查设备..."
DEVICE_COUNT=$(adb devices | grep -v "List" | grep -c "device" || true)
if [ "$DEVICE_COUNT" -eq 0 ]; then
    echo "❌ 没有检测到 USB 连接的手机。请确保："
    echo "   1. 手机已用 USB 线连接电脑"
    echo "   2. 手机开启了 USB 调试（开发者选项）"
    echo "   3. 手机上已授权「允许 USB 调试」"
    exit 1
fi
echo "   ✅ 检测到 $DEVICE_COUNT 台设备"

echo ">>> 清除旧的 adb reverse..."
adb reverse --remove-all 2>/dev/null || true

echo ">>> 映射手机 localhost:$LOCAL_PORT → 本地电脑:$LOCAL_PORT..."
adb reverse tcp:$LOCAL_PORT tcp:$LOCAL_PORT

echo ">>> 启动端口转发: 本地电脑:$LOCAL_PORT → $SERVER_HOST:$SERVER_PORT..."

python3 -c "
import socket, threading, sys

LOCAL = ('0.0.0.0', $LOCAL_PORT)
REMOTE = ('$SERVER_HOST', $SERVER_PORT)

def proxy(client, name):
    try:
        remote = socket.create_connection(REMOTE, timeout=10)
        def forward(src, dst):
            while True:
                data = src.recv(8192)
                if not data: break
                dst.sendall(data)
        t1 = threading.Thread(target=forward, args=(client, remote), daemon=True)
        t2 = threading.Thread(target=forward, args=(remote, client), daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()
    except Exception as e:
        print(f'[{name}] 连接失败: {e}', file=sys.stderr)
    finally:
        try: client.close()
        except: pass
        try: remote.close()
        except: pass

print(f'✅ 桥接已就绪: 手机 localhost:$LOCAL_PORT → $SERVER_HOST:$SERVER_PORT')
print(f'   现在打开 Android App，配置 http://localhost:$LOCAL_PORT')
print(f'   按 Ctrl+C 退出')
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(LOCAL)
server.listen(10)
while True:
    client, addr = server.accept()
    threading.Thread(target=proxy, args=(client, f'{addr}'), daemon=True).start()
" &

PY_PID=$!

echo ""
echo "============================================"
echo "  本地桥接已启动！"
echo "  手机 → localhost:$LOCAL_PORT → $SERVER_HOST:$SERVER_PORT"
echo "  AppConfig: http://localhost:$LOCAL_PORT"
echo "  按 Ctrl+C 停止"
echo "============================================"

# 等用户 Ctrl+C
trap \"kill \$PY_PID 2>/dev/null; adb reverse --remove tcp:\$LOCAL_PORT 2>/dev/null; echo '已断开'; exit 0\" INT TERM
wait \$PY_PID
