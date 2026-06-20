package com.example.shopguideagent.test

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain

object CoroutineTestHelper {
    private val testDispatcher = UnconfinedTestDispatcher()

    @JvmStatic
    fun setMainDispatcher() {
        Dispatchers.setMain(testDispatcher)
    }

    @JvmStatic
    fun resetMainDispatcher() {
        Dispatchers.resetMain()
    }
}
