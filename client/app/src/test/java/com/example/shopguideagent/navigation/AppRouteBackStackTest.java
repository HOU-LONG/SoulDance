package com.example.shopguideagent.navigation;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import org.junit.Test;

public class AppRouteBackStackTest {
    @Test
    public void systemBackMovesOneRouteAtATime() {
        assertEquals(AppRoute.Cart, AppRouteBackStack.previousRoute(AppRoute.Orders));
        assertEquals(AppRoute.Chat, AppRouteBackStack.previousRoute(AppRoute.Cart));
        assertEquals(AppRoute.Home, AppRouteBackStack.previousRoute(AppRoute.Chat));
        assertEquals(AppRoute.Home, AppRouteBackStack.previousRoute(AppRoute.Wardrobe));
        assertEquals(AppRoute.Home, AppRouteBackStack.previousRoute(AppRoute.Tasks));
        assertNull(AppRouteBackStack.previousRoute(AppRoute.Home));
    }
}
