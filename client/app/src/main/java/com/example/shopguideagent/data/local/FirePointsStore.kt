package com.example.shopguideagent.data.local

import android.content.SharedPreferences

interface FirePointsStore {
    fun load(userId: String): Int
    fun save(userId: String, value: Int)
}

class SharedPreferencesFirePointsStore(
    private val preferences: SharedPreferences,
) : FirePointsStore {
    override fun load(userId: String): Int = preferences.getInt(key(userId), DEFAULT)
    override fun save(userId: String, value: Int) {
        preferences.edit().putInt(key(userId), value).apply()
    }
    private fun key(userId: String): String = "fire_points_$userId"
    companion object { const val DEFAULT = 700 }
}

class InMemoryFirePointsStore : FirePointsStore {
    private val store = mutableMapOf<String, Int>()
    override fun load(userId: String): Int = store[userId] ?: 700
    override fun save(userId: String, value: Int) { store[userId] = value }
}
