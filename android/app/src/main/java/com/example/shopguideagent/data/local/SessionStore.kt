package com.example.shopguideagent.data.local

import com.example.shopguideagent.config.UserSession

class SessionStore {
    fun currentSessionId(): String = UserSession.DEFAULT_SESSION_ID
}
