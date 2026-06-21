# SoulDance Release Acceptance and Demo Readiness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the completed gap-fill A/B/C work into a repeatable release acceptance and real-device demo readiness flow.

**Architecture:** Do not add new product features in this phase. Add a release acceptance CLI for the automated gate, then document the manual Cloudflare/device demo gate. Automated checks cover backend tests, fixed eval scenarios, Android unit tests and debug APK build, shell syntax checks, and a non-live-port `/health` smoke. Manual checks stay in documentation because the Cloudflare temporary domain and physical device state are runtime-dependent.

**Tech Stack:** Python 3.12, pytest, FastAPI eval runner, Android Gradle/JBR, Bash, Cloudflare tunnel.

---

## Scope

Already completed and not repeated here:

- SQLite ORM/data baseline and dependency baseline.
- Android token-confirmed order flow.
- SQLite `product_chunks`, fine-grained chunking, BM25 + JSON embedding + RRF retrieval.
- Realtime `ack/seq/trace_id`, timeout degradation, lightweight observability, fixed eval runner.

This plan only implements release/demo readiness:

- One automated acceptance entry point.
- One manual demo checklist.
- Failure handling rules that keep bugfix work narrow.

Explicitly out of scope:

- PostgreSQL, pgvector, Redis, Docker.
- Image upload or visual understanding.
- A/B experimentation and conversion analytics.
- New recommendation algorithms or broad Android UI rewrites.

## File Structure

| File | Responsibility |
|------|----------------|
| `server/scripts/run_release_acceptance.py` | Run or dry-run the release acceptance matrix. |
| `server/tests/test_release_acceptance_cli.py` | Verify the CLI exposes the full matrix, supports selected checks, and reports unknown checks. |
| `docs/demo-readiness.md` | Manual device checklist, Cloudflare steps, demo script, and failure handling rules. |
| `docs/acceptance-tests.md` | Document the release acceptance CLI entry point. |
| `docs/runbook.md` | Document the release/demo readiness workflow. |

## Task 1: Release Acceptance CLI

**Files:**
- Create: `server/scripts/run_release_acceptance.py`
- Test: `server/tests/test_release_acceptance_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

Run:

```bash
cd /home/huadabioa/houlong/SoulDance
env/venv_shopguide_backend/bin/python -m pytest server/tests/test_release_acceptance_cli.py -q
```

Expected: FAIL because `server/scripts/run_release_acceptance.py` does not exist.

- [ ] **Step 2: Implement CLI check registry**

The CLI must expose these checks in order:

```text
backend-tests
eval-runner
android-build
script-syntax
host-health-smoke
```

- [ ] **Step 3: Implement dry-run and check selection**

Commands:

```bash
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --list-checks
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --dry-run --check eval-runner --check android-build
```

Expected: JSON output only; no tests or builds execute.

- [ ] **Step 4: Implement real execution**

Commands:

```bash
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check backend-tests
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check eval-runner
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check script-syntax
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check android-build
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check host-health-smoke
```

Expected: each selected check exits `0`; the first failing check stops the matrix.

## Task 2: Demo Readiness Documentation

**Files:**
- Create: `docs/demo-readiness.md`
- Modify: `docs/acceptance-tests.md`
- Modify: `docs/runbook.md`

- [ ] **Step 1: Document the pre-demo automated gate**

Add the release CLI as the canonical command before a demo or handoff.

- [ ] **Step 2: Document Cloudflare/manual device checks**

The checklist must keep Cloudflare tunnel as the preferred path and avoid `adb reverse` as the default.

- [ ] **Step 3: Document demo script**

Cover:

```text
chat -> primary product card -> product follow-up with focus_product_id -> cart -> address selection -> confirmation_token checkout -> voice/TTS smoke -> websocket reconnect/error handling
```

## Task 3: Run Release Acceptance

**Files:**
- No production edits unless a check fails.

- [ ] **Step 1: Run targeted CLI test**

```bash
env/venv_shopguide_backend/bin/python -m pytest server/tests/test_release_acceptance_cli.py -q
```

Expected: PASS.

- [ ] **Step 2: Run non-device automated checks**

```bash
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check backend-tests --check eval-runner --check script-syntax
```

Expected: all selected checks exit `0`.

- [ ] **Step 3: Run Android build gate**

```bash
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check android-build
```

Expected: Gradle unit tests and debug APK build pass.

- [ ] **Step 4: Run host health smoke**

```bash
env/venv_shopguide_backend/bin/python server/scripts/run_release_acceptance.py --check host-health-smoke
```

Expected: `/health` returns HTTP 200 on a non-live port and the smoke process is stopped.

## Task 4: Manual Device Demo Gate

**Files:**
- Update `docs/demo-readiness.md` only if the real-device path changes.

- [ ] **Step 1: Start backend and Cloudflare tunnel**

Use the current remote backend and temporary Cloudflare domain.

- [ ] **Step 2: Rebuild and install APK**

Use the APK from:

```text
client/app/build/outputs/apk/debug/app-debug.apk
```

- [ ] **Step 3: Walk the demo script**

Record the current tunnel domain, APK path, backend commit, eval result, and any skipped manual step.

## Bugfix Rule

If any automated or manual gate fails, do not broaden scope. Create a small follow-up plan named:

```text
docs/superpowers/plans/YYYY-MM-DD-release-acceptance-<failure-area>-fix.md
```

Each fix plan should start from a failing regression test or a reproducible manual step.
