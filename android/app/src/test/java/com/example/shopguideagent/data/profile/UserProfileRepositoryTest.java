package com.example.shopguideagent.data.profile;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class UserProfileRepositoryTest {
    @Test
    public void readsAndPersistsAvatarUri() {
        InMemoryAvatarUriStore store = new InMemoryAvatarUriStore("content://avatar/old");
        UserProfileRepository repository = new UserProfileRepository(store);

        assertEquals("content://avatar/old", repository.getState().getValue().getAvatarUri());

        repository.updateAvatarUri("content://avatar/new");

        assertEquals("content://avatar/new", store.getAvatarUri());
        assertEquals("content://avatar/new", repository.getState().getValue().getAvatarUri());
    }
}
