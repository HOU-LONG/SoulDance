# SoulDance Android Client

Native Android app for the ShopGuide Agent experience.

## Build

```bash
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"

# Unit tests
./gradlew :app:testDebugUnitTest --no-daemon

# Build APK (auto-checks tunnel + auto-updates AppConfig URL)
./gradlew :app:assembleDebug --no-daemon
```

APK output:

```text
app/build/outputs/apk/debug/app-debug.apk
```

Remote absolute APK path:

```text
/home/huadabioa/houlong/SoulDance/client/app/build/outputs/apk/debug/app-debug.apk
```

## Auto-Incrementing Version

`versionCode` and `versionName` are generated from `git rev-list --count HEAD` at build time. Each new commit automatically increments both (`versionCode` = commit count, `versionName` = `1.0.<commit-count>`). Falls back to `1` when `.git` is unavailable. No manual version bump needed.

## Pre-Build Tunnel Check

Gradle runs `client/scripts/ensure_tunnel.sh` before every build to:

1. Verify the backend is running on `127.0.0.1:8000` (auto-start if needed)
2. Check the current Cloudflare tunnel URL is reachable
3. If the tunnel has restarted with a new hostname, auto-update `AppConfig.kt`
4. Pass through when services are already running (< 1s overhead)

Skip the check when working offline:

```bash
SKIP_TUNNEL_CHECK=true ./gradlew :app:assembleDebug
```

## Runtime Config

Backend URLs live in:

```text
app/src/main/java/com/example/shopguideagent/config/AppConfig.kt
```

Three connection options are available (uncomment the one you need):

| Option | Use Case |
|--------|----------|
| Cloudflare Tunnel | Real device over the internet (auto-managed by pre-build script) |
| `http://10.0.2.2:8000` | Android emulator → host localhost |
| LAN IP / adb reverse | Real device on the same network |

## Session History & User Switching

- `ChatHistoryRepository` stores chat history per `user_id` as JSON in SharedPreferences, keeping at most 30 sessions.
- Old Base64 history format is migrated read-only on first load.
- `SessionsApi` exposes `listSessions()` / `getSession(id)` / `deleteSession(id)`; all requests carry `X-User-Id`.
- `ChatViewModel.onUserSwitched(userId)` persists the current session, reloads local history for the new user, fetches the backend latest session, and reconnects the WebSocket.

## Client Boundary

The app should display backend-returned products only. Keep product recommendation, filtering, cart mutation truth, LLM keys, ASR keys, and TTS keys on the server.

Product follow-up requests must include `focus_product_id` so a BottomSheet question stays bound to the selected product.
