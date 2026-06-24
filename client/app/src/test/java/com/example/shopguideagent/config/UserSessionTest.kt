package com.example.shopguideagent.config

import android.content.SharedPreferences
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)

class UserSessionTest {

    private fun fakePrefs(): SharedPreferences {
        return object : SharedPreferences {
            private val store = mutableMapOf<String, Any?>()

            override fun getAll(): MutableMap<String, *> = store.toMutableMap()

            override fun getString(key: String?, defValue: String?): String? {
                @Suppress("UNCHECKED_CAST")
                return store[key] as? String? ?: defValue
            }

            override fun getStringSet(key: String?, defValues: MutableSet<String>?): MutableSet<String>? {
                @Suppress("UNCHECKED_CAST")
                return store[key] as? MutableSet<String>? ?: defValues
            }

            override fun getInt(key: String?, defValue: Int): Int {
                @Suppress("UNCHECKED_CAST")
                return store[key] as? Int ?: defValue
            }

            override fun getLong(key: String?, defValue: Long): Long {
                @Suppress("UNCHECKED_CAST")
                return store[key] as? Long ?: defValue
            }

            override fun getFloat(key: String?, defValue: Float): Float {
                @Suppress("UNCHECKED_CAST")
                return store[key] as? Float ?: defValue
            }

            override fun getBoolean(key: String?, defValue: Boolean): Boolean {
                @Suppress("UNCHECKED_CAST")
                return store[key] as? Boolean ?: defValue
            }

            override fun contains(key: String?): Boolean = store.containsKey(key)

            override fun edit(): SharedPreferences.Editor {
                return object : SharedPreferences.Editor {
                    override fun putString(key: String?, value: String?): SharedPreferences.Editor {
                        if (key != null) store[key] = value
                        return this
                    }

                    override fun putStringSet(key: String?, values: MutableSet<String>?): SharedPreferences.Editor {
                        if (key != null) store[key] = values
                        return this
                    }

                    override fun putInt(key: String?, value: Int): SharedPreferences.Editor {
                        if (key != null) store[key] = value
                        return this
                    }

                    override fun putLong(key: String?, value: Long): SharedPreferences.Editor {
                        if (key != null) store[key] = value
                        return this
                    }

                    override fun putFloat(key: String?, value: Float): SharedPreferences.Editor {
                        if (key != null) store[key] = value
                        return this
                    }

                    override fun putBoolean(key: String?, value: Boolean): SharedPreferences.Editor {
                        if (key != null) store[key] = value
                        return this
                    }

                    override fun remove(key: String?): SharedPreferences.Editor {
                        if (key != null) store.remove(key)
                        return this
                    }

                    override fun clear(): SharedPreferences.Editor {
                        store.clear()
                        return this
                    }

                    override fun commit(): Boolean = true

                    override fun apply() {}
                }
            }

            override fun registerOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}
            override fun unregisterOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}
        }
    }

    @Test
    fun `preset users contains exactly three demo entries`() {
        assertEquals(3, UserSession.PRESET_USERS.size)
        assertTrue(UserSession.PRESET_USERS.all { it.id.matches(Regex("^[a-z0-9_]{1,64}$")) })
    }

    @Test
    fun `cold start defaults to first preset user`() = runTest {
        val session = UserSession.create(fakePrefs())
        assertEquals(UserSession.PRESET_USERS.first().id, session.currentUserId.first())
    }

    @Test
    fun `setCurrentUserId persists and updates flow`() = runTest {
        val prefs = fakePrefs()
        val session = UserSession.create(prefs)
        session.setCurrentUserId(UserSession.PRESET_USERS[1].id)
        assertEquals(UserSession.PRESET_USERS[1].id, session.currentUserId.first())
        // A second instance backed by the same prefs sees the persisted value.
        val reopened = UserSession.create(prefs)
        assertEquals(UserSession.PRESET_USERS[1].id, reopened.currentUserId.first())
    }

    @Test
    fun `setCurrentUserId rejects unknown id`() {
        val session = UserSession.create(fakePrefs())
        assertThrows(IllegalArgumentException::class.java) { session.setCurrentUserId("not_a_preset") }
    }
}
