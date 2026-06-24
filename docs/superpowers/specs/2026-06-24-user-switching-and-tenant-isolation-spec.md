# User Switching And Tenant Isolation Spec

## Goal

Add a lightweight, demo-grade user-switching capability so the ShopGuide Agent can prove tenant isolation end to end: the same `session_id` belongs to different users carries different data, and no compression / cart / firePoints state leaks between users.

This spec precedes the existing `2026-06-24-session-context-compression-spec.md` Task 4 (compression persistence). After this spec ships, that Task 4 reduces to "add the compression table + dual-key repository on top of the existing user-id identity layer."

## Existing Baseline

- Client-side `UserSession` is a Kotlin `object` with two compile-time constants: `USER_ID = "demo_user"` and `DEFAULT_SESSION_ID = "demo_session_001"`. Every `CartViewModel`, `ChatViewModel`, `SpriteHomeViewModel`, `SessionStore`, and `ChatMessage.toJson` reads them directly, so the entire client is effectively pinned to a single user.
- `ChatHistoryDrawer.DrawerUserFooter` is already a clickable surface with a single behavior ("点击更换头像"). Its layout has room for a dropdown without changing the drawer width.
- Backend `/api/profile/{user_id}` already accepts `user_id` as a path parameter and `UserProfileStore` is keyed by `user_id`. Outside that one endpoint, no API surface knows about `user_id`.
- Database: `SessionState.session_id` is `unique=True`. `Cart.session_id` is `unique=True`. `FeedbackEvent` carries only `session_id`. None of these tables have a `user_id` column today; introducing one requires a one-time migration script (the project has SQLAlchemy models but no Alembic directory).
- Repositories (`SessionRepository.get/save`, `cart_repository`, etc.) take `session_id` only and return whatever row matches it. There is no per-user gate.
- No network code today sends a user identifier — neither REST nor WebSocket. Adding one means introducing a single header that all transports honor.

## Required Principles

1. Demo-grade, not production identity. No login, no password, no token, no OAuth. The point is to make `(user_id, session_id)` isolation observable, not to authenticate anyone.

2. Single source of truth for the current user id. The client must have exactly one mutable, persisted source for `currentUserId`. Every view model, network call, and local persistence key derives from it. Reading the value from two different places is a contract bug.

3. Transport-uniform identity. The user id travels in a single `X-User-Id` header across REST and WebSocket. Business request bodies do not carry it. Adding a new endpoint must not require a new way of expressing identity.

4. Backward compatibility by default. A request without `X-User-Id` resolves to `user_id="anonymous"`. Existing tests, curl probes, and not-yet-updated clients keep working. No new endpoint may hard-require the header in this spec; later specs can tighten it.

5. Switching users is a session boundary, not a fresh boot. When the user picks a different identity, the client:
   - Closes the current WebSocket cleanly.
   - Asks the backend `GET /api/sessions/latest` for that user's most recent session id.
   - Reopens transport against that session id.
   - Reloads cart, firePoints, and chat history from the new user's locally-keyed storage.
   The full app state must observably change; if any panel still shows the previous user's data after a switch, that is a bug.

6. Tenant isolation is non-negotiable for SessionState. Once this spec ships, the database forbids two rows in `session_states` with the same `(user_id, session_id)` and allows two rows with the same `session_id` if `user_id` differs. Any write that does not include `user_id` is a repository bug, not a recoverable runtime branch.

7. Local persistence keys must include the user id. `CartPersistenceStore` already uses per-user keys (`cart_items_<userId>`). Anything that does not (SharedPreferences for firePoints, session lists) must move to the same pattern in this spec. A switch must never accidentally read another user's keys.

8. Identity validation is narrow and explicit. The backend accepts only `^[a-z0-9_]{1,64}$` user ids. Anything else returns HTTP 400 with a clear error code so client bugs cannot silently corrupt the ledger.

9. Concurrency stays at last-write-wins. If the same user opens the same `session_id` from two devices, both writes go through and the later one wins — same as today. This spec does not add row-level locking; that is the compression spec's concern (its lifecycle integration task).

## Non-Goals For The First Implementation

- No login, password, account creation, deletion, or admin UI.
- No backend endpoint for listing or creating users. The 3 preset users live in client code; the backend infers them on first write.
- No per-user theming, UI personalization, or feature flags. The only thing that changes on switch is data scoping.
- No Hilt/DI refactor. Continue passing the current `UserSession` reference the way the existing view models do.
- No changes to existing Android navigation, drawer width, theme tokens, or sprite home layout.
- No changes to the compression layer yet — that is the next spec's job. This spec only ensures `user_id` is available everywhere the compression layer will need it.

## Acceptance Criteria

1. Footer dropdown — `ChatHistoryDrawer.DrawerUserFooter` becomes a clickable dropdown; tapping it shows the current user plus the other two preset users plus the existing "点击更换头像" action; selecting another user invokes `UserSession.setCurrentUserId(...)`.

2. Persisted identity — `UserSession.currentUserId` is backed by SharedPreferences. Restarting the app restores the last selected user. Cold install defaults to `demo_user_a`.

3. Header transport — every REST request and the WebSocket handshake carries `X-User-Id: <currentUserId>`. Tested at the OkHttp interceptor layer (REST) and in the WebSocket connect headers map.

4. Server dependency — `get_current_user_id(request: Request)` reads `X-User-Id`, validates against `^[a-z0-9_]{1,64}$`, returns `"anonymous"` on missing, returns HTTP 400 on malformed.

5. Session latest endpoint — `GET /api/sessions/latest` returns `{"session_id": "<latest_or_newly_minted>"}` for the requesting user. Two users hit the same endpoint and get different ids; a never-seen user gets a freshly minted id without raising.

6. Database — `session_states` has a non-null `user_id` column (default `'anonymous'` for migration safety), the old single-column `session_id` unique index is removed, and `UniqueConstraint("user_id", "session_id")` is enforced. Same for `carts` (Cart still uses `session_id`, but `(user_id, session_id)` is the new uniqueness key).

7. Repository signatures — `SessionRepository.get(user_id, session_id)`, `SessionRepository.save(user_id, context)`, `cart_repository.get(user_id, session_id)`, `cart_repository.save(user_id, ...)`. Calling without `user_id` is a `TypeError`, not a silent default.

8. Migration script — `server/scripts/migrate_session_tenant_keys.py` rewrites the existing SQLite (and any future Postgres) schema in place, fills existing rows with `user_id='anonymous'`, and is idempotent (re-running is a no-op). On Postgres, the script runs `ALTER TABLE ... ADD COLUMN`, drops the old single-column unique index, and adds the new composite. On SQLite, where a column-level unique constraint is implemented as an autoindex that cannot be dropped in place, the script rebuilds the table: create `session_states_new`, copy rows with `user_id='anonymous'`, drop `session_states`, rename `session_states_new` to `session_states`, recreate the secondary indexes. Same shape for `carts`.

9. Client local state — switching users reloads `CartViewModel`, `SpriteHomeViewModel.firePoints`, and the chat history drawer from per-user-keyed storage. The previous user's data must not be visible after a switch.

10. Switching flow — switching `demo_user_a → demo_user_b → demo_user_a` returns the user to exactly the state they had before the first switch (cart contents, firePoints, last session id), proving the round trip is lossless.

11. Backward compatibility — every existing backend test continues to pass without being adapted to send `X-User-Id`. Missing-header requests must keep landing in the `anonymous` tenant.

12. Isolation tests — new `server/tests/test_tenant_isolation.py` proves that two users with the same `session_id` cannot read each other's state, and that the database constraint actually rejects a same-`(user_id, session_id)` second insert.
