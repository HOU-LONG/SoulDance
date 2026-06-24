package com.example.shopguideagent.config

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class PresetUser(
    val id: String,
    val displayName: String,
    val avatarHint: String,
)

/**
 * 演示级用户身份单例。
 *
 * - PRESET_USERS：写死在客户端的 3 个用户。后端按需懒创建对应记录。
 * - currentUserId：可观察的当前用户 id，全应用唯一来源。
 * - setCurrentUserId：切换并持久化到 SharedPreferences。
 *
 * 不要在新代码里读 UserSession.USER_ID 之类的常量。
 */
class UserSession private constructor(
    private val preferences: SharedPreferences,
) {
    private val _currentUserId = MutableStateFlow(
        preferences.getString(KEY_CURRENT_USER_ID, null) ?: PRESET_USERS.first().id
    )
    val currentUserId: StateFlow<String> = _currentUserId.asStateFlow()

    fun setCurrentUserId(id: String) {
        require(PRESET_USERS.any { it.id == id }) { "Unknown preset user id: $id" }
        preferences.edit().putString(KEY_CURRENT_USER_ID, id).apply()
        _currentUserId.value = id
    }

    companion object {
        const val DEFAULT_SESSION_ID = "demo_session_001"

        val PRESET_USERS: List<PresetUser> = listOf(
            PresetUser("demo_user_a", "演示用户 A", "A"),
            PresetUser("demo_user_b", "演示用户 B", "B"),
            PresetUser("demo_user_c", "演示用户 C", "C"),
        )

        private const val KEY_CURRENT_USER_ID = "current_user_id"
        private const val PREFS_NAME = "shopguide_user_session"

        @Volatile private var instance: UserSession? = null

        fun create(preferences: SharedPreferences): UserSession =
            UserSession(preferences)

        fun get(context: Context): UserSession {
            val existing = instance
            if (existing != null) return existing
            synchronized(this) {
                val again = instance
                if (again != null) return again
                val prefs = context.applicationContext.getSharedPreferences(
                    PREFS_NAME, Context.MODE_PRIVATE
                )
                val created = UserSession(prefs)
                instance = created
                return created
            }
        }
    }
}
