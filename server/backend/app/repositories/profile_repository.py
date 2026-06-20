from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import UserProfile
from ..models import UserFeedbackProfile


class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: str) -> UserFeedbackProfile | None:
        row = self.db.query(UserProfile).filter_by(user_id=user_id).first()
        if row is None:
            return None
        # 将 ORM 列映射为 Pydantic 模型字段
        return UserFeedbackProfile(
            user_id=row.user_id,
            total_ratings=row.total_ratings,
            liked_product_ids=row.liked_product_ids,
            disliked_product_ids=row.disliked_product_ids,
            signals=row.signals,
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )

    def save(self, profile: UserFeedbackProfile) -> None:
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        row = self.db.query(UserProfile).filter_by(user_id=profile.user_id).first()
        if row is None:
            row = UserProfile(user_id=profile.user_id)
            self.db.add(row)
        row.total_ratings = profile.total_ratings
        row.liked_product_ids = profile.liked_product_ids
        row.disliked_product_ids = profile.disliked_product_ids
        row.signals = [s.model_dump(mode="json") for s in profile.signals]
        row.updated_at = datetime.now(timezone.utc)
        self.db.flush()
