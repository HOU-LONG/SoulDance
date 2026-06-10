from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .feedback_aggregator import FeedbackAggregator
from .feedback_store import FeedbackStore
from .models import FeedbackSignal, UserFeedbackProfile

logger = logging.getLogger(__name__)


class UserProfileStore:
    """跨 session 的用户偏好画像持久化。

    每个 user_id 对应一个 UserFeedbackProfile，
    session 关闭时将当轮反馈合并进长期画像。
    """

    def __init__(self, persist_dir: str | Path | None = None):
        self._profiles: dict[str, UserFeedbackProfile] = {}
        self.persist_dir = Path(persist_dir) if persist_dir else None
        if self.persist_dir:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def get(self, user_id: str) -> UserFeedbackProfile:
        """获取或创建用户画像。"""
        if user_id not in self._profiles:
            loaded = self._load_one(user_id)
            self._profiles[user_id] = loaded or UserFeedbackProfile(user_id=user_id)
        return self._profiles[user_id]

    def save(self, profile: UserFeedbackProfile) -> None:
        """保存单个用户画像。"""
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        self._profiles[profile.user_id] = profile
        if self.persist_dir:
            self._save_one(profile)

    def merge_session_feedback(
        self,
        user_id: str,
        signal: FeedbackSignal,
    ) -> UserFeedbackProfile:
        """将一轮 session 的反馈信号合并进长期画像。"""
        profile = self.get(user_id)
        profile.signals.append(signal)
        # 保留最近 20 轮
        profile.signals = profile.signals[-20:]

        # 累积品牌权重
        for brand, weight in signal.brand_weights.items():
            prev = next((s.brand_weights.get(brand, 0) for s in profile.signals[:-1] if brand in s.brand_weights), 0)
            signal.brand_weights[brand] = (prev + weight) / 2  # EMA 平滑

        profile.total_ratings += 1
        self.save(profile)
        return profile

    def to_preference_context(self, user_id: str) -> dict:
        """将用户画像转为 LLM 可用的偏好上下文。"""
        profile = self.get(user_id)
        if not profile.signals:
            return {}

        latest = profile.signals[-1]
        avoid_brands = [b for b, w in latest.brand_weights.items() if w < -1.0]
        prefer_tags = list(set(latest.preference_tags))[:5]

        ctx: dict = {}
        if avoid_brands:
            ctx["avoid_brands"] = avoid_brands
        if latest.price_preference:
            ctx["price_tendency"] = latest.price_preference
        if prefer_tags:
            ctx["prefer_tags"] = prefer_tags
        if profile.liked_product_ids:
            ctx["liked_count"] = len(profile.liked_product_ids)
        return ctx

    # ---- 持久化 ----

    def _path(self, user_id: str) -> Path:
        safe = user_id.replace("/", "_").replace("\\", "_")
        return self.persist_dir / f"{safe}.json"  # type: ignore[union-attr]

    def _load_one(self, user_id: str) -> UserFeedbackProfile | None:
        if not self.persist_dir:
            return None
        path = self._path(user_id)
        if not path.exists():
            return None
        try:
            return UserFeedbackProfile.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed to load profile %s", user_id, exc_info=True)
            return None

    def _save_one(self, profile: UserFeedbackProfile) -> None:
        if not self.persist_dir:
            return
        self._path(profile.user_id).write_text(profile.model_dump_json(), encoding="utf-8")

    def _load(self) -> None:
        if not self.persist_dir:
            return
        for path in self.persist_dir.glob("*.json"):
            try:
                profile = UserFeedbackProfile.model_validate_json(path.read_text(encoding="utf-8"))
                self._profiles[profile.user_id] = profile
            except Exception:
                logger.warning("Failed to load profile file %s", path.name, exc_info=True)
