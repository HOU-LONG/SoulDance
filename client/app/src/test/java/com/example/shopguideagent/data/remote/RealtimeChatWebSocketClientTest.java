package com.example.shopguideagent.data.remote;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import com.example.shopguideagent.data.model.QuickActionUiModel;
import com.example.shopguideagent.data.model.RealtimeEvent;

import org.junit.Test;

import java.lang.reflect.Method;

public class RealtimeChatWebSocketClientTest {
    @Test
    public void audioDeltaAcceptsBackendDataFieldAsBase64Payload() throws Exception {
        RealtimeChatWebSocketClient client = new RealtimeChatWebSocketClient();
        Method parseEvent = RealtimeChatWebSocketClient.class.getDeclaredMethod("parseEvent", String.class);
        parseEvent.setAccessible(true);

        RealtimeEvent event = (RealtimeEvent) parseEvent.invoke(
                client,
                "{\"type\":\"audio_delta\",\"message_id\":\"m1\",\"data\":\"ZmFrZQ==\",\"encoding\":\"pcm_s16le\",\"sample_rate\":24000}"
        );

        assertTrue(event instanceof RealtimeEvent.AudioDelta);
        RealtimeEvent.AudioDelta audio = (RealtimeEvent.AudioDelta) event;
        assertEquals("m1", audio.getMessageId());
        assertEquals("ZmFrZQ==", audio.getAudioBase64());
        assertEquals("pcm_s16le", audio.getEncoding());
        assertEquals(24000, audio.getSampleRate());
    }

    @Test
    public void quickActionsParseLabelsAndMessagesFromBackendPayload() throws Exception {
        RealtimeChatWebSocketClient client = new RealtimeChatWebSocketClient();
        Method parseEvent = RealtimeChatWebSocketClient.class.getDeclaredMethod("parseEvent", String.class);
        parseEvent.setAccessible(true);

        RealtimeEvent event = (RealtimeEvent) parseEvent.invoke(
                client,
                "{\"type\":\"quick_actions\",\"message_id\":\"m2\",\"actions\":["
                        + "{\"label\":\"Avoid BrandA\",\"message\":\"Do not recommend BrandA\"},"
                        + "{\"label\":\"Cheaper\",\"message\":\"Find a cheaper option\"}"
                        + "]}"
        );

        assertTrue(event instanceof RealtimeEvent.QuickActions);
        RealtimeEvent.QuickActions quickActions = (RealtimeEvent.QuickActions) event;
        assertEquals("m2", quickActions.getMessageId());
        assertEquals(2, quickActions.getActions().size());
        QuickActionUiModel first = quickActions.getActions().get(0);
        assertEquals("Avoid BrandA", first.getLabel());
        assertEquals("Do not recommend BrandA", first.getMessage());
    }
}
