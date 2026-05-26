class TTSAdapter:
    async def synthesize_events(self, text: str, enabled: bool = False) -> list[dict]:
        """TTS placeholder.

        v0 intentionally does not call qwen3_tts or return audio_delta events.
        Later wiring can call the local Qwen3-TTS service here and stream
        pcm_s16le chunks using the Android protocol's audio_delta event.
        """

        return []
