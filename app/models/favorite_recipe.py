from datetime import datetime

from .db import db


class FavoriteRecipe(db.Model):
    __tablename__ = "favorite_recipes"

    id = db.Column(db.String(64), primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "image_url": self.image_url,
            "created_at": self.created_at.isoformat(),
        }

