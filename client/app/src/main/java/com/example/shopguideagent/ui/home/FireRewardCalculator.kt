package com.example.shopguideagent.ui.home

import kotlin.math.floor
import kotlin.math.min

object FireRewardCalculator {
    fun bonusRate(level: Int): Float = when {
        level <= 10 -> 0f
        level <= 20 -> 0.10f
        level <= 30 -> 0.20f
        else -> 0.30f
    }

    fun reward(base: Int, level: Int): Int {
        val rate = 1 + bonusRate(level)
        return floor(base * rate).toInt()
    }

    fun discountAmount(firePoints: Int, orderAmount: Double): Double {
        val fromFire = firePoints / 100.0
        val maxDiscount = orderAmount * 0.10
        return min(fromFire, maxDiscount)
    }
}
