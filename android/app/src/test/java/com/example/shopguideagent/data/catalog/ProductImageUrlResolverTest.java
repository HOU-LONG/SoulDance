package com.example.shopguideagent.data.catalog;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

import org.junit.Test;

import java.nio.charset.StandardCharsets;

public class ProductImageUrlResolverTest {
    @Test
    public void assetUrlRepairsMojibakeDatasetPath() {
        String readablePath = "1_\u7f8e\u5986\u62a4\u80a4/images/p_beauty_001_live.jpg";
        String mojibakePath = new String(
                readablePath.getBytes(StandardCharsets.UTF_8),
                StandardCharsets.ISO_8859_1
        );
        String url = ProductImageUrlResolver.assetUrl(mojibakePath);

        assertEquals(
                "file:///android_asset/" + readablePath,
                url
        );
    }

    @Test
    public void assetUrlKeepsReadableDatasetPath() {
        String readablePath = "2_\u6570\u7801\u7535\u5b50/images/p_digital_001_live.jpg";
        String url = ProductImageUrlResolver.assetUrl(readablePath);

        assertEquals(
                "file:///android_asset/" + readablePath,
                url
        );
    }

    @Test
    public void remoteUrlExpandsServerRelativePaths() {
        String url = ProductImageUrlResolver.remoteUrl(
                "/static/images/p_beauty_001_live.jpg",
                "http://10.0.2.2:8000"
        );

        assertEquals("http://10.0.2.2:8000/static/images/p_beauty_001_live.jpg", url);
    }

    @Test
    public void remoteUrlRebasesPrivateBackendAssetUrlsToConfiguredBackend() {
        String url = ProductImageUrlResolver.remoteUrl(
                "http://192.168.3.116:8000/assets/products/1_%E7%BE%8E%E5%A6%86/images/p_beauty_001_live.jpg",
                "https://continually-replication-allowing-editions.trycloudflare.com/"
        );

        assertEquals(
                "https://continually-replication-allowing-editions.trycloudflare.com/assets/products/1_%E7%BE%8E%E5%A6%86/images/p_beauty_001_live.jpg",
                url
        );
    }

    @Test
    public void blankUrlReturnsNull() {
        assertNull(ProductImageUrlResolver.assetUrl(" "));
        assertNull(ProductImageUrlResolver.remoteUrl("", "http://10.0.2.2:8000"));
    }
}
