from __future__ import annotations

import os

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from ..services.groq_service import GroqService
from ..services.image_service import (
    detect_ingredients_placeholder,
    detect_ingredients_with_groq_vision,
    save_upload,
)
from ..services.recipe_service import RecipeService
from ..utils.validators import DetectIngredientsResponse

bp = Blueprint("main", __name__)


@bp.get("/")
def landing():
    return render_template("landing.html")


@bp.get("/app")
def app_home():
    return render_template("app.html")


@bp.get("/try")
def try_cooking_mode():
    demo_ingredients = ["egg", "tomato", "cheese", "pasta"]

    groq = GroqService(
        api_key=current_app.config.get("GROQ_API_KEY"),
        base_url=current_app.config.get("GROQ_BASE_URL"),
        model=current_app.config.get("GROQ_MODEL"),
        timeout_s=current_app.config.get("GROQ_TIMEOUT_SECONDS", 35),
    )
    svc = RecipeService(groq=groq)

    try:
        recipes = svc.generate_recipes(ingredients=demo_ingredients, count=4)
    except Exception as e:
        current_app.logger.exception("Recipe generation failed in /try: %s", e)
        recipes = svc.generate_recipes_local(ingredients=demo_ingredients, count=4)

    # Populate the server-side recipe cache so recipe_detail_page can find them.
    # Only store IDs in the session cookie — the full payloads (with images)
    # live in _RECIPES_CACHE to stay well under the ~4 KB cookie limit.
    from .recipe_routes import _RECIPES_CACHE
    ids: list[str] = []
    for r in recipes:
        rid = str(r.get("id") or "").strip()
        if rid:
            _RECIPES_CACHE[rid] = r
            ids.append(rid)
    session["last_recipe_ids"] = ids   # matches the key recipe_routes reads
    session.modified = True

    if recipes:
        rid = recipes[0].get("id")
        return redirect(url_for("recipes.recipe_detail_page", recipe_id=rid, mode="cooking"))

    return redirect(url_for("main.app_home"))


@bp.post("/api/detect-ingredients")
def api_detect_ingredients():
    if "image" not in request.files:
        return jsonify({"error": "missing_image"}), 400

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)

    try:
        path = save_upload(request.files["image"], upload_folder)

        groq_key = current_app.config.get("GROQ_API_KEY")
        if groq_key:
            groq = GroqService(
                api_key=groq_key,
                base_url=current_app.config.get("GROQ_BASE_URL"),
                model=current_app.config.get("GROQ_MODEL"),
                timeout_s=current_app.config.get("GROQ_TIMEOUT_SECONDS", 35),
            )
            ingredients = detect_ingredients_with_groq_vision(
                image_path=path,
                groq=groq,
                vision_model=current_app.config.get("GROQ_VISION_MODEL"),
            )
        else:
            current_app.logger.warning(
                "GROQ_API_KEY is not configured. Falling back to placeholder ingredients."
            )
            ingredients = detect_ingredients_placeholder(path)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.exception("Ingredient detection failed: %s", e)
        ingredients = detect_ingredients_placeholder("")

    payload = DetectIngredientsResponse(ingredients=ingredients).model_dump()
    return jsonify(payload)