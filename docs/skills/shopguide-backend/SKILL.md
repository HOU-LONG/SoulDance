---
name: shopguide-backend
description: Use when changing the SoulDance ShopGuide FastAPI backend, RAG planning, session memory, WebSocket events, cart actions, or demo evaluation cases.
---

# ShopGuide Backend Workflow

## Read First

1. `README_backend.md`
2. `docs/interaction_protocol.md`
3. `docs/rag_decision_log.md`
4. `backend/app/agent.py`
5. `backend/app/planner_agent.py`
6. `tests/test_agent_core.py`

## Rules

- Do not put API keys in source files.
- Hard constraints are filters, not ranking penalties.
- Keep new WebSocket events optional so older Android clients can ignore them.
- For interaction changes, write a failing test before editing backend behavior.
- Prefer session-state reference resolution for `刚才那款`, `第一款`, and cart commands.

## Verification

Run:

```bash
env/venv_shopguide_backend/bin/python -m pytest tests/test_agent_core.py tests/test_api.py -v
```

For a manual smoke test:

```bash
ARK_API_KEY="$ARK_API_KEY" bash scripts/start_backend.sh
SHOPGUIDE_BASE_URL=http://127.0.0.1:18080 env/venv_shopguide_backend/bin/python scripts/smoke_demo.py
```
