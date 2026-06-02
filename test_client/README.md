# ShopGuide Active Clarification Test Client

This is a small manual test client for verifying the ShopGuide backend active clarification WebSocket flow.

## Backend Connection

The client defaults to:

```text
ws://127.0.0.1:18080/ws/chat
```

If the backend is running on `mix_A100`, open a local tunnel first:

```bash
ssh -L 18080:127.0.0.1:18080 mix_A100
```

Backend path on the server:

```bash
cd /home/huadabioa/houlong/SoulDance
```

Optional health check:

```bash
curl http://127.0.0.1:18080/health
```

The page also loads `/health` automatically and shows `llm=fake/doubao`, retriever mode, product count, current turn intent, retrieval mode, and WebSocket event count. Use `llm=doubao` when verifying real LLM/Semantic Agent intent recognition.

## Run

Open this file in a browser:

```text
/Users/acc/Documents/Souldance/souldance_impl/test_client/index.html
```

## Build

```bash
npm run build
```

This client has no third-party dependencies. `npm run build` only checks that the static page contains the required WebSocket event handling strings.

## Manual Flow

1. Connect the WebSocket.
2. Click `含糊手机`.
3. Confirm that `clarification_request` appears and no product cards appear.
4. Click `拍照优先`.
5. Confirm that the same session receives phone product cards and no repeated clarification.
6. Check that `text_delta` events receive increasing event numbers in the raw log; HTML can stream normally when the backend emits chunks.
