package com.example.shopguideagent.voice

enum class VoiceInputUiState {
    Idle,
    Recording,
    CancelPending,
}

enum class VoiceInputResult {
    None,
    Submit,
    Cancel,
}

class VoiceInputStateMachine(
    private val cancelThresholdPx: Float = -56f,
) {
    var state: VoiceInputUiState = VoiceInputUiState.Idle
        private set

    fun onPress(): VoiceInputUiState {
        state = VoiceInputUiState.Recording
        return state
    }

    fun onDrag(totalDragY: Float): VoiceInputUiState {
        state = if (totalDragY <= cancelThresholdPx) {
            VoiceInputUiState.CancelPending
        } else {
            VoiceInputUiState.Recording
        }
        return state
    }

    fun onRelease(): VoiceInputResult {
        val result = when (state) {
            VoiceInputUiState.CancelPending -> VoiceInputResult.Cancel
            VoiceInputUiState.Recording -> VoiceInputResult.Submit
            VoiceInputUiState.Idle -> VoiceInputResult.None
        }
        state = VoiceInputUiState.Idle
        return result
    }

    fun reset() {
        state = VoiceInputUiState.Idle
    }
}
