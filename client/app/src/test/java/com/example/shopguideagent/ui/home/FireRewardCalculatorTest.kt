package com.example.shopguideagent.ui.home

import org.junit.Assert.assertEquals
import org.junit.Test

class FireRewardCalculatorTest {
    @Test
    fun bonusRateForLevelRanges() {
        assertEquals(0f, FireRewardCalculator.bonusRate(1), 0.001f)
        assertEquals(0f, FireRewardCalculator.bonusRate(10), 0.001f)
        assertEquals(0.10f, FireRewardCalculator.bonusRate(11), 0.001f)
        assertEquals(0.10f, FireRewardCalculator.bonusRate(20), 0.001f)
        assertEquals(0.20f, FireRewardCalculator.bonusRate(21), 0.001f)
        assertEquals(0.20f, FireRewardCalculator.bonusRate(30), 0.001f)
        assertEquals(0.30f, FireRewardCalculator.bonusRate(31), 0.001f)
    }

    @Test
    fun rewardAppliesFloorBonus() {
        assertEquals(8, FireRewardCalculator.reward(8, 10))
        assertEquals(8, FireRewardCalculator.reward(8, 11)) // 8 * 1.1 = 8.8 -> 8
        assertEquals(24, FireRewardCalculator.reward(20, 21)) // 20 * 1.2 = 24
    }

    @Test
    fun discountAmountRespectsCapAndBalance() {
        assertEquals(1.0, FireRewardCalculator.discountAmount(100, 200.0), 0.001)
        assertEquals(10.0, FireRewardCalculator.discountAmount(2000, 100.0), 0.001) // cap 10%
        assertEquals(0.0, FireRewardCalculator.discountAmount(0, 100.0), 0.001)
    }
}
