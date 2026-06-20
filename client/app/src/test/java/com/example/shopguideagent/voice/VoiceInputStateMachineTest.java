package com.example.shopguideagent.voice;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class VoiceInputStateMachineTest {
    @Test
    public void pressStartsRecording() {
        VoiceInputStateMachine machine = new VoiceInputStateMachine();

        assertEquals(VoiceInputUiState.Recording, machine.onPress());
    }

    @Test
    public void upwardDragMarksCancelPending() {
        VoiceInputStateMachine machine = new VoiceInputStateMachine();
        machine.onPress();

        assertEquals(VoiceInputUiState.CancelPending, machine.onDrag(-80f));
    }

    @Test
    public void releaseSubmitsUnlessCancelPending() {
        VoiceInputStateMachine submitMachine = new VoiceInputStateMachine();
        submitMachine.onPress();
        assertEquals(VoiceInputResult.Submit, submitMachine.onRelease());

        VoiceInputStateMachine cancelMachine = new VoiceInputStateMachine();
        cancelMachine.onPress();
        cancelMachine.onDrag(-80f);
        assertEquals(VoiceInputResult.Cancel, cancelMachine.onRelease());
    }
}
