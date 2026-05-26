cd /home/huadabioa/houlong/SoulDance

curl -sS -X POST http://127.0.0.1:18880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "model": "qwen3-tts",
    "input": "Hello, this is a Qwen3 TTS test.",
    "task_type": "VoiceDesign",
    "instructions": "A calm, clear female narrator voice.",
    "response_format": "wav",
    "stream": false
  }' \
  --output logs/qwen3_tts_test.wav

file logs/qwen3_tts_test.wav