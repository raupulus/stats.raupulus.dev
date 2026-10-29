"""Unit tests for TelegramCollector using respx."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.telegram import TelegramCollector
from social_stats.config.profiles import AccountConfig


@respx.mock
async def test_telegram_public_preview_and_landing_fallback() -> None:
    """
    Verify TelegramCollector extracts subscribers and latest message views
    from /s/{handle}, falls back to /{handle} for landing-only channels,
    and isolates non-existent channels.
    """
    preview_html = """
    <html><body>
      <div class="tgme_channel_info_counters">
        <div class="tgme_channel_info_counter">
          <span class="counter_value">12</span>
          <span class="counter_type">subscribers</span>
        </div>
      </div>
      <div class="tgme_widget_message_wrap">
        <div class="tgme_widget_message" data-post="raupulus_diffusion/297">
          <span class="tgme_widget_message_views">88</span>
          <time datetime="2026-10-25T10:00:00+00:00"></time>
        </div>
      </div>
      <div class="tgme_widget_message_wrap">
        <div class="tgme_widget_message" data-post="raupulus_diffusion/298">
          <span class="tgme_widget_message_views">101</span>
          <time datetime="2026-10-28T18:30:00+00:00"></time>
        </div>
      </div>
    </body></html>
    """
    respx.get("https://t.me/s/raupulus_diffusion").mock(
        return_value=httpx.Response(200, text=preview_html)
    )

    # Landing-only channel where /s/ lacks counter block
    respx.get("https://t.me/s/community_news").mock(
        return_value=httpx.Response(200, text="<html><body>Redirected landing</body></html>")
    )
    respx.get("https://t.me/community_news").mock(
        return_value=httpx.Response(
            200,
            text='<html><body><div class="tgme_page_extra">2.5K subscribers</div></body></html>',
        )
    )

    # Invalid handle returning generic Telegram landing page with no metrics
    respx.get("https://t.me/s/nonexistent_xyz").mock(
        return_value=httpx.Response(200, text="<html><body>Telegram Messenger</body></html>")
    )
    respx.get("https://t.me/nonexistent_xyz").mock(
        return_value=httpx.Response(200, text="<html><body>Telegram Messenger</body></html>")
    )

    collector = TelegramCollector()
    accounts = [
        AccountConfig(
            handle="https://t.me/raupulus_diffusion",
            account_key="raupulus_diffusion",
            platform="telegram",
        ),
        AccountConfig(
            handle="community_news",
            account_key="community_news",
            platform="telegram",
        ),
        AccountConfig(
            handle="nonexistent_xyz",
            account_key="nonexistent_xyz",
            platform="telegram",
        ),
    ]
    results = await collector.collect_batch(accounts)

    assert "raupulus_diffusion" in results
    m1 = results["raupulus_diffusion"]
    assert m1.followers_total == 12
    assert m1.posts_total == 298
    assert m1.views_total == 101
    assert m1.latest_post is not None
    assert m1.latest_post.post_id == "298"
    assert m1.latest_post.url == "https://t.me/raupulus_diffusion/298"
    assert m1.latest_post.views == 101

    assert "community_news" in results
    assert results["community_news"].followers_total == 2500

    assert "nonexistent_xyz" not in results
    assert "nonexistent_xyz" in collector.last_errors
