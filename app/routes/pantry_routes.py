from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..models import PantryItem, db
from ..services.ingredient_service import normalize_ingredient

bp = Blueprint("pantry", __name__)


@bp.get("/api/pantry")
def api_get_pantry():
    items = PantryItem.query.order_by(PantryItem.name.asc()).all()
    return jsonify({"items": [i.to_dict() for i in items]})


@bp.post("/api/pantry")
def api_add_pantry():
    data = request.get_json(silent=True) or {}
    name = normalize_ingredient(str(data.get("name", "")))
    if not name:
        return jsonify({"error": "missing_name"}), 400

    existing = PantryItem.query.filter_by(name=name).first()
    if existing:
        return jsonify({"item": existing.to_dict(), "created": False})

    item = PantryItem(name=name)
    db.session.add(item)
    db.session.commit()
    return jsonify({"item": item.to_dict(), "created": True}), 201


@bp.delete("/api/pantry/<item>")
def api_delete_pantry(item: str):
    name = normalize_ingredient(item)
    obj = PantryItem.query.filter_by(name=name).first()
    if not obj:
        return jsonify({"error": "not_found"}), 404
    db.session.delete(obj)
    db.session.commit()
    return jsonify({"deleted": True, "name": name})

