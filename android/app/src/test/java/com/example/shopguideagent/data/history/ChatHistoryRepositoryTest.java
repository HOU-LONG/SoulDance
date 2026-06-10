package com.example.shopguideagent.data.history;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import com.example.shopguideagent.data.model.ChatMessageUiModel;
import com.example.shopguideagent.data.model.MessageRole;

import org.junit.Test;

import java.util.Collections;

public class ChatHistoryRepositoryTest {
    @Test
    public void savesAndRestoresSessionsFromStore() {
        InMemoryChatHistoryStore store = new InMemoryChatHistoryStore("");
        ChatHistoryRepository repository = new ChatHistoryRepository(store);

        ChatMessageUiModel message = new ChatMessageUiModel(
                "m1",
                MessageRole.User,
                "想买防晒",
                false,
                100L,
                0,
                Collections.emptyList(),
                null
        );
        repository.saveSession("s1", "防晒推荐", Collections.singletonList(message), 200L);

        ChatHistoryRepository restored = new ChatHistoryRepository(store);

        assertEquals(1, restored.getState().getValue().getSessions().size());
        assertEquals("s1", restored.getState().getValue().getCurrentSessionId());
        assertEquals("想买防晒", restored.getState().getValue().getSessions().get(0).getMessages().get(0).getText());
    }

    @Test
    public void deleteSessionRemovesItFromStoreAndKeepsCurrentWhenPossible() {
        InMemoryChatHistoryStore store = new InMemoryChatHistoryStore("");
        ChatHistoryRepository repository = new ChatHistoryRepository(store);
        ChatMessageUiModel message = new ChatMessageUiModel(
                "m1",
                MessageRole.User,
                "想买手机",
                false,
                100L,
                0,
                Collections.emptyList(),
                null
        );
        repository.saveSession("s1", "手机推荐", Collections.singletonList(message), 100L);
        repository.saveSession("s2", "咖啡推荐", Collections.singletonList(message), 200L);

        repository.deleteSession("s2");

        assertEquals(1, repository.getState().getValue().getSessions().size());
        assertEquals("s1", repository.getState().getValue().getCurrentSessionId());

        ChatHistoryRepository restored = new ChatHistoryRepository(store);
        assertEquals(1, restored.getState().getValue().getSessions().size());
        assertEquals("s1", restored.getState().getValue().getCurrentSessionId());
    }

    @Test
    public void deleteLastSessionClearsCurrentSessionId() {
        InMemoryChatHistoryStore store = new InMemoryChatHistoryStore("");
        ChatHistoryRepository repository = new ChatHistoryRepository(store);
        ChatMessageUiModel message = new ChatMessageUiModel(
                "m1",
                MessageRole.User,
                "想买手机",
                false,
                100L,
                0,
                Collections.emptyList(),
                null
        );
        repository.saveSession("s1", "手机推荐", Collections.singletonList(message), 100L);

        repository.deleteSession("s1");

        assertEquals(0, repository.getState().getValue().getSessions().size());
        assertNull(repository.getState().getValue().getCurrentSessionId());
    }
}
