package com.example.shopguideagent.data.profile

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

interface AvatarUriStore {
    fun getAvatarUri(): String?
    fun setAvatarUri(uri: String?)
}

class UserProfileRepository(
    private val avatarUriStore: AvatarUriStore,
) {
    private val _state = MutableStateFlow(UserProfileState(avatarUri = avatarUriStore.getAvatarUri()))
    val state: StateFlow<UserProfileState> = _state.asStateFlow()

    fun updateAvatarUri(uri: String?) {
        avatarUriStore.setAvatarUri(uri)
        _state.value = _state.value.copy(avatarUri = uri)
    }
}

class SharedPreferencesAvatarUriStore(
    private val preferences: SharedPreferences,
) : AvatarUriStore {
    override fun getAvatarUri(): String? =
        preferences.getString(KEY_AVATAR_URI, null)

    override fun setAvatarUri(uri: String?) {
        preferences.edit().putString(KEY_AVATAR_URI, uri).apply()
    }

    companion object {
        private const val KEY_AVATAR_URI = "avatar_uri"
    }
}

class InMemoryAvatarUriStore(
    private var avatarUri: String? = null,
) : AvatarUriStore {
    override fun getAvatarUri(): String? = avatarUri

    override fun setAvatarUri(uri: String?) {
        avatarUri = uri
    }
}

fun userProfileRepository(context: Context): UserProfileRepository {
    val preferences = context.applicationContext.getSharedPreferences("shopguide_profile", Context.MODE_PRIVATE)
    return UserProfileRepository(SharedPreferencesAvatarUriStore(preferences))
}
