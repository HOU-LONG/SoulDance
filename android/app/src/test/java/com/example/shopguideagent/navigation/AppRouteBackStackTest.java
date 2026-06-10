package com.example.shopguideagent.navigation;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import org.junit.Test;

public class AppRouteBackStackTest {
    @Test
    public void systemBackMovesOneRouteAtATime() {
        assertEquals(AppRoute.Cart, AppRouteBackStack.previousRoute(AppRoute.Orders));
        assertEquals(AppRoute.Chat, AppRouteBackStack.previousRoute(AppRoute.Cart));
        assertNull(AppRouteBackStack.previousRoute(AppRoute.Chat));
    }
}
