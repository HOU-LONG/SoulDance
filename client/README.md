# SoulDance Android Client

Native Android app for the ShopGuide Agent experience.

## Build

```bash
export JAVA_HOME=/home/huadabioa/houlong/android-studio/jbr
export ANDROID_HOME=/home/huadabioa/houlong/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew :app:testDebugUnitTest --no-daemon
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

## Runtime Config

Backend URLs live in:

```text
app/src/main/java/com/example/shopguideagent/config/AppConfig.kt
```

Real-device debugging should use the Cloudflare tunnel URL configured there. Rebuild the APK after changing the tunnel domain.

## Session History & User Switching

- `ChatHistoryRepository` stores chat history per `user_id` as JSON in SharedPreferences, keeping at most 30 sessions.
- Old Base64 history format is migrated read-only on first load.
- `SessionsApi` exposes `listSessions()` / `getSession(id)` / `deleteSession(id)`; all requests carry `X-User-Id`.
- `ChatViewModel.onUserSwitched(userId)` persists the current session, reloads local history for the new user, fetches the backend latest session, and reconnects the WebSocket.

## Client Boundary

The app should display backend-returned products only. Keep product recommendation, filtering, cart mutation truth, LLM keys, ASR keys, and TTS keys on the server.

Product follow-up requests must include `focus_product_id` so a BottomSheet question stays bound to the selected product.
