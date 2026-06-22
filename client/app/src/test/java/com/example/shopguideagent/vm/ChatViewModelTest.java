package com.example.shopguideagent.vm;

import static com.example.shopguideagent.vm.ChatViewModelKt.visibleProductCountForStreaming;
import static com.example.shopguideagent.vm.ChatViewModelKt.interruptedStreamMessage;
import static com.example.shopguideagent.vm.ChatViewModelKt.shouldExitRecommendationSkeleton;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;

import com.example.shopguideagent.data.catalog.ListProductCatalog;
import com.example.shopguideagent.data.history.ChatHistoryRepository;
import com.example.shopguideagent.data.history.ChatSessionUiModel;
import com.example.shopguideagent.data.history.InMemoryChatHistoryStore;
import com.example.shopguideagent.data.model.MessageRole;
import com.example.shopguideagent.data.model.ProductFollowUpPayload;
import com.example.shopguideagent.data.model.ProductUiModel;
import com.example.shopguideagent.data.model.QuickActionUiModel;
import com.example.shopguideagent.data.model.RealtimeEvent;
import com.example.shopguideagent.data.remote.RealtimeChatWebSocketClient;

import com.example.shopguideagent.test.CoroutineTestHelper;
import kotlinx.coroutines.flow.Flow;
import kotlinx.coroutines.flow.FlowKt;
import org.json.JSONObject;
import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import java.lang.reflect.Method;
import java.util.Arrays;

public class ChatViewModelTest {
    @BeforeClass
    public static void setupClass() {
        CoroutineTestHelper.setMainDispatcher();
    }

    @AfterClass
    public static void tearDownClass() {
        CoroutineTestHelper.resetMainDispatcher();
    }

    @Test
    public void sendMessageAddsUserMessageAndAssistantRecommendationFromCatalog() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();

        viewModel.sendMessage("Recommend a cleanser for oily skin under 100");
        completeRecommendation(viewModel, product("cleanser", "Gentle cleanser", Arrays.asList("cleanser", "oil skin")));

        assertEquals(3, viewModel.getUiState().getValue().getMessages().size());
        assertEquals(MessageRole.User, viewModel.getUiState().getValue().getMessages().get(1).getRole());
        assertEquals(MessageRole.Assistant, viewModel.getUiState().getValue().getMessages().get(2).getRole());
        assertFalse(viewModel.getUiState().getValue().isSending());
        org.junit.Assert.assertTrue(
                viewModel.getUiState().getValue().getMessages().get(2).getProducts().get(0).getImageUrl()
                        .startsWith("file:///android_asset/")
        );
    }

    @Test
    public void multipleMessagesAppendInsteadOfReplacingHistory() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();

        viewModel.sendMessage("Recommend a cleanser for oily skin under 100");
        completeRecommendation(viewModel, product("cleanser", "Gentle cleanser", Arrays.asList("cleanser", "oil skin")));
        viewModel.sendMessage("Is there a cheaper option?");
        completeRecommendation(viewModel, product("sunscreen", "Daily sunscreen", Arrays.asList("sunscreen", "outdoor")));

        assertEquals(5, viewModel.getUiState().getValue().getMessages().size());
        assertEquals("Is there a cheaper option?", viewModel.getUiState().getValue().getMessages().get(3).getText());
        assertEquals(MessageRole.Assistant, viewModel.getUiState().getValue().getMessages().get(4).getRole());
    }

    @Test
    public void productFollowUpUsesFocusedProductContext() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();
        viewModel.sendMessage("Recommend a sunscreen");
        completeRecommendation(viewModel, product("sunscreen", "Daily sunscreen", Arrays.asList("sunscreen", "outdoor")));
        ProductUiModel focused = viewModel.getUiState().getValue().getMessages().get(2).getProducts().get(0);

        viewModel.sendProductFollowUp(focused, "Need an option under 100");
        handleRealtimeEvent(viewModel, new RealtimeEvent.FocusTextDelta("focus", "Need an option under 100"));
        handleRealtimeEvent(
                viewModel,
                new RealtimeEvent.ReplacementProduct(
                        "focus",
                        product("cleanser", "Gentle cleanser", Arrays.asList("cleanser", "oil skin"))
                )
        );
        handleRealtimeEvent(viewModel, new RealtimeEvent.FocusDone("focus"));

        assertEquals(5, viewModel.getUiState().getValue().getMessages().size());
        assertEquals(focused.getProductId(), viewModel.getUiState().getValue().getFocus().getSelectedProduct().getProductId());
        org.junit.Assert.assertTrue(viewModel.getUiState().getValue().getFocus().getResponseText().contains("Need an option under 100"));
        assertEquals("cleanser", viewModel.getUiState().getValue().getFocus().getReplacementProducts().get(0).getProductId());
        assertEquals(MessageRole.Assistant, viewModel.getUiState().getValue().getMessages().get(4).getRole());
        org.junit.Assert.assertTrue(viewModel.getUiState().getValue().getMessages().get(4).getText().contains("Need an option under 100"));
        assertEquals("cleanser", viewModel.getUiState().getValue().getMessages().get(4).getProducts().get(0).getProductId());
        assertFalse(viewModel.getUiState().getValue().getMessages().get(4).isStreaming());
    }

    @Test
    public void productFollowUpPlainTextDeltaWritesToVisibleAssistantMessage() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();
        ProductUiModel focused = product("sunscreen", "Daily sunscreen", Arrays.asList("sunscreen", "outdoor"));

        viewModel.sendProductFollowUp(focused, "Need a cheaper option");
        handleRealtimeEvent(viewModel, new RealtimeEvent.TextDelta("backend_message", "Visible follow-up reply"));
        handleRealtimeEvent(viewModel, new RealtimeEvent.FocusDone("backend_message"));

        assertEquals(MessageRole.Assistant, viewModel.getUiState().getValue().getMessages().get(2).getRole());
        org.junit.Assert.assertTrue(
                viewModel.getUiState().getValue().getMessages().get(2).getText().contains("Visible follow-up reply")
        );
        assertFalse(viewModel.getUiState().getValue().getMessages().get(2).isStreaming());
    }

    @Test
    public void sendProductFollowUpStoresLastPayloadFocusProductIdAndText() {
        ProductUiModel focused = product("focused-product", "Focused product", Arrays.asList("first"));
        ChatViewModel viewModel = new ChatViewModel(
                new ListProductCatalog(Arrays.asList(focused)),
                new ChatHistoryRepository(new InMemoryChatHistoryStore("")),
                new NoopRealtimeChatWebSocketClient()
        );

        viewModel.sendProductFollowUp(focused, "Keep this exact follow-up text");

        ProductFollowUpPayload payload = viewModel.getLastProductFollowUpPayload();
        assertNotNull(payload);
        assertEquals("focused-product", payload.getFocusProductId());
        assertEquals("Keep this exact follow-up text", payload.getMessage());
    }

    @Test
    public void getLastProductFollowUpPayloadJsonReturnsExactSnakeCaseContract() throws Exception {
        ProductUiModel active = product("active-product", "Active product", Arrays.asList("first"));
        ChatViewModel viewModel = new ChatViewModel(
                new ListProductCatalog(Arrays.asList(active)),
                new ChatHistoryRepository(new InMemoryChatHistoryStore("")),
                new NoopRealtimeChatWebSocketClient()
        );

        viewModel.sendProductFollowUp(active, "Raw follow-up text");

        JSONObject payload = viewModel.getLastProductFollowUpPayloadJson();
        assertNotNull(payload);
        assertEquals("product_followup", payload.getString("type"));
        assertEquals("active-product", payload.getString("focus_product_id"));
        assertEquals("Raw follow-up text", payload.getString("message"));
    }

    @Test
    public void productFollowUpUsesNextSourceOrderedReplacementWithoutPromotingIt() throws Exception {
        ProductUiModel focused = product("focused", "Focused product", Arrays.asList("first"));
        ProductUiModel sourceReplacement = product("source-replacement", "Source replacement", Arrays.asList("second"));
        ProductUiModel queryMatchedLater = product("query-matched-later", "Exact follow up query match", Arrays.asList("Exact follow up query match"));
        ChatViewModel viewModel = new ChatViewModel(
                new ListProductCatalog(Arrays.asList(focused, sourceReplacement, queryMatchedLater)),
                new ChatHistoryRepository(new InMemoryChatHistoryStore("")),
                new NoopRealtimeChatWebSocketClient()
        );

        viewModel.sendMessage("initial request");
        completeRecommendation(viewModel, focused);
        ProductUiModel selected = viewModel.getUiState().getValue().getMessages().get(2).getProducts().get(0);
        viewModel.sendProductFollowUp(selected, "Exact follow up query match");
        handleRealtimeEvent(viewModel, new RealtimeEvent.FocusTextDelta("focus", "next source-provided comparable option"));
        handleRealtimeEvent(viewModel, new RealtimeEvent.ReplacementProduct("focus", sourceReplacement));
        handleRealtimeEvent(viewModel, new RealtimeEvent.FocusDone("focus"));

        ProductUiModel replacement = viewModel.getUiState().getValue().getMessages().get(4).getProducts().get(0);
        String reply = viewModel.getUiState().getValue().getMessages().get(4).getText();
        assertEquals("source-replacement", replacement.getProductId());
        assertFalse(replacement.isPrimary());
        org.junit.Assert.assertTrue(reply.contains("next source-provided comparable option"));
    }

    @Test
    public void selectSessionClearsFocusedProductState() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();
        viewModel.sendMessage("initial request");
        completeRecommendation(viewModel, product("cleanser", "Gentle cleanser", Arrays.asList("cleanser", "oil skin")));
        ProductUiModel focused = viewModel.getUiState().getValue().getMessages().get(2).getProducts().get(0);
        viewModel.sendProductFollowUp(focused, "follow-up text");
        assertNotNull(viewModel.getUiState().getValue().getFocus().getSelectedProduct());

        ChatSessionUiModel otherSession = new ChatSessionUiModel(
                "other-session",
                "Other session",
                42L,
                Arrays.asList(viewModel.getUiState().getValue().getMessages().get(0))
        );

        viewModel.selectSession(otherSession);

        assertNull(viewModel.getUiState().getValue().getFocus().getSelectedProduct());
        assertEquals("", viewModel.getUiState().getValue().getFocus().getResponseText());
        assertEquals(0, viewModel.getUiState().getValue().getFocus().getReplacementProducts().size());
        assertFalse(viewModel.getUiState().getValue().getFocus().isStreaming());
        assertFalse(viewModel.getUiState().getValue().isSending());
        assertNull(viewModel.getUiState().getValue().getErrorMessage());
        assertEquals(1, viewModel.getUiState().getValue().getMessages().size());
    }

    @Test
    public void sendMessageStreamingIgnoresConcurrentSendWhileSending() {
        ChatViewModel viewModel = viewModelWithCatalog();

        viewModel.sendMessageStreaming("first request");
        viewModel.sendMessageStreaming("second request");

        assertEquals(3, viewModel.getUiState().getValue().getMessages().size());
        assertEquals("first request", viewModel.getUiState().getValue().getMessages().get(1).getText());
    }

    @Test
    public void sendProductFollowUpAppendsWhileStreamingSendIsInProgress() {
        ChatViewModel viewModel = viewModelWithCatalog();
        ProductUiModel focused = product("focused-product", "Focused product", Arrays.asList("first"));

        viewModel.sendMessageStreaming("first request");
        org.junit.Assert.assertTrue(viewModel.getUiState().getValue().isSending());

        viewModel.sendProductFollowUp(focused, "follow-up during stream");

        assertEquals(5, viewModel.getUiState().getValue().getMessages().size());
        org.junit.Assert.assertTrue(viewModel.getUiState().getValue().isSending());
        assertEquals("focused-product", viewModel.getLastProductFollowUpPayload().getFocusProductId());
        assertEquals("follow-up during stream", viewModel.getLastProductFollowUpPayload().getMessage());
        assertEquals(MessageRole.User, viewModel.getUiState().getValue().getMessages().get(3).getRole());
        assertEquals(MessageRole.Assistant, viewModel.getUiState().getValue().getMessages().get(4).getRole());
        org.junit.Assert.assertTrue(viewModel.getUiState().getValue().getMessages().get(4).isStreaming());

        viewModel.sendMessageStreaming("second request");

        assertEquals(5, viewModel.getUiState().getValue().getMessages().size());
    }

    @Test
    public void streamingProductRevealProgressesBeforeFinalTextChunk() {
        assertEquals(0, visibleProductCountForStreaming(0, 12, 3));
        assertEquals(1, visibleProductCountForStreaming(3, 12, 3));
        assertEquals(2, visibleProductCountForStreaming(6, 12, 3));
        assertEquals(3, visibleProductCountForStreaming(9, 12, 3));
    }

    @Test
    public void recommendationSkeletonTimeoutOnlyExitsActiveStreamsPastTimeout() {
        assertFalse(shouldExitRecommendationSkeleton(true, 1000L, 8000L));
        org.junit.Assert.assertTrue(shouldExitRecommendationSkeleton(true, 9000L, 8000L));
        assertFalse(shouldExitRecommendationSkeleton(false, 9000L, 8000L));
    }

    @Test
    public void staleTimeoutCannotInterruptNewerAssistantStream() {
        assertFalse(
                com.example.shopguideagent.vm.ChatViewModelKt.shouldInterruptTimedOutStream(
                        "assistant_old",
                        "assistant_new",
                        true
                )
        );
        org.junit.Assert.assertTrue(
                com.example.shopguideagent.vm.ChatViewModelKt.shouldInterruptTimedOutStream(
                        "assistant_current",
                        "assistant_current",
                        true
                )
        );
        assertFalse(
                com.example.shopguideagent.vm.ChatViewModelKt.shouldInterruptTimedOutStream(
                        "assistant_current",
                        "assistant_current",
                        false
                )
        );
    }

    @Test
    public void interruptedStreamMessagePreservesPartialText() {
        org.junit.Assert.assertTrue(interruptedStreamMessage("partial reply", "Retry").contains("partial reply"));
        org.junit.Assert.assertTrue(interruptedStreamMessage("partial reply", "Retry").contains("Retry"));
        assertEquals("Retry", interruptedStreamMessage("", "Retry"));
    }

    @Test
    public void handleStreamInterruptedExitsLoadingAndExposesRetry() {
        ChatViewModel viewModel = viewModelWithCatalog();
        viewModel.sendMessageStreaming("first request");
        String assistantId = viewModel.getUiState().getValue().getMessages().get(2).getId();

        viewModel.handleStreamInterrupted(assistantId, "Connection interrupted. Retry?");

        assertFalse(viewModel.getUiState().getValue().isSending());
        assertEquals("first request", viewModel.getUiState().getValue().getRetryMessageText());
        assertEquals("Connection interrupted. Retry?", viewModel.getUiState().getValue().getErrorMessage());
        assertFalse(viewModel.getUiState().getValue().getMessages().get(2).isStreaming());
        assertEquals(
                viewModel.getUiState().getValue().getMessages().get(2).getProducts().size(),
                viewModel.getUiState().getValue().getMessages().get(2).getExpectedProductCount()
        );
    }

    @Test
    public void cartUpdateRendersBackendMessageAndBadgeCount() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();
        viewModel.sendMessageStreaming("将两份雀巢咖啡加入购物车");
        String assistantId = viewModel.getUiState().getValue().getMessages().get(2).getId();

        Method handler = ChatViewModel.class.getDeclaredMethod("handleRealtimeEvent", RealtimeEvent.class);
        handler.setAccessible(true);
        handler.invoke(
                viewModel,
                new RealtimeEvent.CartUpdate(
                        assistantId,
                        2,
                        "已把雀巢咖啡加入购物车。",
                        "add_to_cart",
                        "p_food_002"
                )
        );

        assertEquals(2, viewModel.getUiState().getValue().getCartBadgeCount());
        org.junit.Assert.assertTrue(viewModel.getUiState().getValue().getCartSyncVersion() > 0);
        org.junit.Assert.assertTrue(
                viewModel.getUiState().getValue().getMessages().get(2).getText().contains("雀巢咖啡")
        );
    }

    @Test
    public void failedCartUpdateRendersMessageWithoutBadgeOrSyncChange() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();
        viewModel.sendMessageStreaming("将小米手机加入购物车");
        String assistantId = viewModel.getUiState().getValue().getMessages().get(2).getId();

        Method handler = ChatViewModel.class.getDeclaredMethod("handleRealtimeEvent", RealtimeEvent.class);
        handler.setAccessible(true);
        handler.invoke(
                viewModel,
                new RealtimeEvent.CartUpdate(
                        assistantId,
                        0,
                        "我找到了多个可能的商品，请说完整型号。",
                        "add_to_cart",
                        null,
                        false
                )
        );

        assertEquals(0, viewModel.getUiState().getValue().getCartBadgeCount());
        assertEquals(0L, viewModel.getUiState().getValue().getCartSyncVersion());
        org.junit.Assert.assertTrue(
                viewModel.getUiState().getValue().getMessages().get(2).getText().contains("完整型号")
        );
    }

    @Test
    public void ackEventIsIgnoredWithoutAddingAssistantMessageOrError() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();
        viewModel.sendMessageStreaming("first request");
        String assistantId = viewModel.getUiState().getValue().getMessages().get(2).getId();

        Method handler = ChatViewModel.class.getDeclaredMethod("handleRealtimeEvent", RealtimeEvent.class);
        handler.setAccessible(true);
        handler.invoke(
                viewModel,
                new RealtimeEvent.Ack(assistantId, "trace_1", 0)
        );

        assertEquals(3, viewModel.getUiState().getValue().getMessages().size());
        assertNull(viewModel.getUiState().getValue().getErrorMessage());
        assertEquals(assistantId, viewModel.getUiState().getValue().getMessages().get(2).getId());
        org.junit.Assert.assertTrue(viewModel.getUiState().getValue().getMessages().get(2).isStreaming());
    }

    @Test
    public void quickActionsAttachToActiveAssistantMessage() throws Exception {
        ChatViewModel viewModel = viewModelWithCatalog();
        viewModel.sendMessageStreaming("recommend sunscreen");
        String assistantId = viewModel.getUiState().getValue().getMessages().get(2).getId();

        Method handler = ChatViewModel.class.getDeclaredMethod("handleRealtimeEvent", RealtimeEvent.class);
        handler.setAccessible(true);
        handler.invoke(
                viewModel,
                new RealtimeEvent.QuickActions(
                        assistantId,
                        Arrays.asList(
                                new QuickActionUiModel("Avoid BrandA", "Do not recommend BrandA"),
                                new QuickActionUiModel("Cheaper", "Find a cheaper option")
                        )
                )
        );

        assertEquals(
                "Avoid BrandA",
                viewModel.getUiState().getValue().getMessages().get(2).getQuickActions().get(0).getLabel()
        );
        assertEquals(
                "Do not recommend BrandA",
                viewModel.getUiState().getValue().getMessages().get(2).getQuickActions().get(0).getMessage()
        );
    }

    private ChatViewModel viewModelWithCatalog() {
        ProductUiModel clean = productWithImage("cleanser", "Gentle cleanser", Arrays.asList("cleanser", "oil skin"));
        ProductUiModel sunscreen = productWithImage("sunscreen", "Daily sunscreen", Arrays.asList("sunscreen", "outdoor"));
        return new ChatViewModel(
                new ListProductCatalog(Arrays.asList(clean, sunscreen)),
                new ChatHistoryRepository(new InMemoryChatHistoryStore("")),
                new NoopRealtimeChatWebSocketClient()
        );
    }

    private static void completeRecommendation(ChatViewModel viewModel, ProductUiModel... products) throws Exception {
        String assistantId = viewModel.getUiState().getValue().getMessages().get(
                viewModel.getUiState().getValue().getMessages().size() - 1
        ).getId();
        handleRealtimeEvent(viewModel, new RealtimeEvent.ProductsStart(assistantId, products.length, "Recommendations"));
        for (int i = 0; i < products.length; i++) {
            handleRealtimeEvent(viewModel, new RealtimeEvent.ProductItem(assistantId, i, products[i]));
        }
        handleRealtimeEvent(viewModel, new RealtimeEvent.ProductsDone(assistantId));
        handleRealtimeEvent(viewModel, new RealtimeEvent.Done(assistantId));
    }

    private static void handleRealtimeEvent(ChatViewModel viewModel, RealtimeEvent event) throws Exception {
        Method handler = ChatViewModel.class.getDeclaredMethod("handleRealtimeEvent", RealtimeEvent.class);
        handler.setAccessible(true);
        handler.invoke(viewModel, event);
    }

    private static class NoopRealtimeChatWebSocketClient extends RealtimeChatWebSocketClient {
        @Override
        public Flow<RealtimeEvent> connect() {
            return FlowKt.emptyFlow();
        }

        @Override
        public boolean sendUserMessage(String sessionId, String message, boolean ttsEnabled) {
            return true;
        }

        @Override
        public boolean sendProductFollowup(String sessionId, String focusProductId, String message, boolean ttsEnabled) {
            return true;
        }
    }

    private ProductUiModel product(String productId, String name, java.util.List<String> tags) {
        return new ProductUiModel(
                productId,
                name,
                99.0,
                null,
                tags,
                "source ordered product",
                null,
                null,
                false
        );
    }

    private ProductUiModel productWithImage(String productId, String name, java.util.List<String> tags) {
        return new ProductUiModel(
                productId,
                name,
                99.0,
                "file:///android_asset/test/" + productId + ".jpg",
                tags,
                "synthetic catalog product",
                null,
                null,
                false
        );
    }
}
