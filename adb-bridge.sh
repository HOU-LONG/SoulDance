#!/usr/bin/env bash
# ==========================================================
# adb-bridge.sh — 把手机通过 USB 桥接到后端服务器
# ==========================================================
# 前提: 手机已通过 USB 连接电脑，USB 调试已开启
# 用法: ./adb-bridge.sh
# 之后 Android AppConfig 填 http://localhost:8000

set -e

# ========== 运行环境检测 ==========
# 这个脚本设计在「本地电脑」上运行（手机 USB 插在这台电脑上）
# 如果在远程服务器（SSH 会话）中运行，会给出警告并退出
if [ -n "${SSH_CONNECTION:-}" ] || [ -n "${SSH_CLIENT:-}" ] || [ -n "${SSH_TTY:-}" ]; then
    echo "⚠️  警告：检测到当前处于 SSH 远程会话中。"
    echo ""
    echo "    adb-bridge.sh 应该在「本地电脑」上运行，而不是远程服务器。"
    echo "    因为手机 USB 只能连接到本地电脑，adb 需要在本地电脑上操作。"
    echo ""
    echo "    正确的架构："
    echo "      本地电脑（插手机）──SSH隧道──→ 远程服务器（跑后端）"
    echo ""
    echo "    如果你在本地电脑运行仍看到此提示，请用以下方式强制运行："
    echo "      SSH_CONNECTION='' ./adb-bridge.sh"
    echo ""
    exit 1
fi
# =================================

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT/env/venv_vllm_cu128}"
PYTHON="${VENV_DIR}/bin/python3"
# 如果虚拟环境里找不到 python3，回退到 PATH 中的 python3
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3 || true)"
fi
if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    echo "❌ 找不到可用的 python3。请检查 Python 环境或设置 VENV_DIR 变量。"
    exit 1
fi

SERVER="${1:-192.168.3.116:8000}"
LOCAL_PORT=8000

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

echo ">>> 映射手机 localhost:$LOCAL_PORT → 电脑:$LOCAL_PORT..."
adb reverse tcp:$LOCAL_PORT tcp:$LOCAL_PORT

echo ">>> 启动端口转发 电脑:$LOCAL_PORT → $SERVER..."

# 用 Python 做端口转发（不需要额外安装任何工具）
"$PYTHON" -c "
import socket, threading, sys

LOCAL = ('0.0.0.0', $LOCAL_PORT)
REMOTE = ('${SERVER%%:*}', ${SERVER##*:})

def proxy(client, name):
    try:
        remote = socket.create_connection(REMOTE, timeout=10)
        def forward(src, dst, direction):
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

print(f'✅ 桥接已就绪: 手机 localhost:$LOCAL_PORT → $SERVER')
print(f'   现在打开 Android App 即可测试。按 Ctrl+C 退出。')
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
echo "  桥接已启动！"
echo "  手机 → localhost:8000 → $SERVER"
echo "  AppConfig: http://localhost:8000"
echo "  按 Ctrl+C 停止"
echo "============================================"

# 等用户 Ctrl+C
trap "kill $PY_PID 2>/dev/null; adb reverse --remove tcp:$LOCAL_PORT 2>/dev/null; echo '已断开'; exit 0" INT TERM
wait $PY_PID
