from __future__ import annotations

import json
from typing import Any, Optional

import requests
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, Response

from ..models import FavoriteRecipe, PantryItem, db
from ..services.groq_service import GroqService
from ..services.ingredient_service import filter_out_staples, normalize_ingredient_list
from ..services.recipe_service import RecipeService, _IMAGE_CACHE, _IMAGE_ERRORS, _CACHE_LOCK
from ..utils.validators import GenerateRecipesRequest, validate_model

bp = Blueprint("recipes", __name__)


# ---------------------------------------------------------------------------
# IN-MEMORY RECIPE CACHE (AVOIDS STORING LARGE IMAGES IN SESSION COOKIE)
# ---------------------------------------------------------------------------

_RECIPES_CACHE: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# SERVICE FACTORY (UPDATED)
# ---------------------------------------------------------------------------


def _recipe_service() -> RecipeService:
    groq = GroqService(
        api_key=current_app.config.get("GROQ_API_KEY"),
        base_url=current_app.config.get("GROQ_BASE_URL"),
        model=current_app.config.get("GROQ_MODEL"),
        timeout_s=current_app.config.get("GROQ_TIMEOUT_SECONDS", 35),
    )

    return RecipeService(groq=groq)


# ---------------------------------------------------------------------------
# SESSION / CACHE HELPERS
# ---------------------------------------------------------------------------


def _get_session_recipes() -> list[dict[str, Any]]:
    """
    Returns the last generated recipes for the current user.

    To keep the browser session cookie small, we only store recipe IDs in
    the signed cookie and keep the full recipe payloads (including images)
    in an in-memory cache on the server.
    """
    ids: list[str] = session.get("last_recipe_ids", [])
    recipes: list[dict[str, Any]] = []
    for rid in ids:
        r = _RECIPES_CACHE.get(str(rid))
        if r is not None:
            recipes.append(r)
    return recipes


def _find_recipe_anywhere(recipe_id: str) -> Optional[dict]:
    # 1) Check in-memory cache first (fast path, includes images).
    cached = _RECIPES_CACHE.get(str(recipe_id))
    if cached is not None:
        return cached

    # 2) Check last session recipes (IDs) for backwards compatibility.
    for r in _get_session_recipes():
        if r.get("id") == recipe_id:
            return r

    # 3) Finally, check favorites stored in the database.
    fav = FavoriteRecipe.query.filter_by(id=recipe_id).first()
    if fav:
        try:
            return json.loads(fav.payload_json)
        except Exception:
            return None

    return None


# ---------------------------------------------------------------------------
# RECIPES PAGE
# ---------------------------------------------------------------------------

@bp.get("/recipes")
def recipes_page():
    return render_template("recipes.html", recipes=_get_session_recipes())


@bp.get("/recipe/<recipe_id>")
def recipe_detail_page(recipe_id: str):
    recipe = _find_recipe_anywhere(recipe_id)
    if not recipe:
        return render_template("not_found.html", title="Recipe not found"), 404

    mode = request.args.get("mode", "detail")
    return render_template("recipe_detail.html", recipe=recipe, mode=mode)


# ---------------------------------------------------------------------------
# GENERATE RECIPES (UNCHANGED LOGIC, IMAGE NOW HANDLED INSIDE SERVICE)
# ---------------------------------------------------------------------------

@bp.post("/api/generate-recipes")
def api_generate_recipes():
    data = request.get_json(silent=True) or {}

    model, err = validate_model(GenerateRecipesRequest, data)
    if err:
        return jsonify(err.model_dump()), 400

    assert isinstance(model, GenerateRecipesRequest)

    manual = normalize_ingredient_list(model.manual_ingredients)
    detected = normalize_ingredient_list(model.detected_ingredients)
    pantry = normalize_ingredient_list(model.pantry_ingredients)

    if model.mode == "manual":
        ingredients = manual
    elif model.mode == "fridge":
        ingredients = detected
    elif model.mode == "pantry":
        ingredients = pantry
    else:
        ingredients = normalize_ingredient_list(pantry + detected)

    if not ingredients:
        return jsonify({"recipes": []})

    if model.mode == "pantry":
        non_staples = filter_out_staples(pantry)
        if not non_staples:
            return (
                jsonify({
                    "error": "pantry_only_staples",
                    "message": "Pantry-only generation requires at least one non-staple ingredient.",
                    "recipes": [],
                }),
                400,
            )

    try:
        svc = _recipe_service()
        recipes = svc.generate_recipes(
            ingredients=ingredients,
            count=model.count,
            async_images=True,   # return immediately; images polled via /api/recipes/image/<id>
        )

    except RuntimeError as e:
        if str(e) not in {
            "missing_groq_api_key",
            "groq_unauthorized",
            "groq_http_error",
            "groq_request_failed",
        }:
            raise

        svc = _recipe_service()
        recipes = svc.generate_recipes_local(
            ingredients=ingredients,
            count=model.count,
            async_images=True,
        )

    # Store full recipes (including images) ONLY on the server side.
    ids: list[str] = []
    for r in recipes:
        rid = str(r.get("id") or "").strip()
        if not rid:
            continue
        _RECIPES_CACHE[rid] = r
        ids.append(rid)

    # Store only lightweight list of IDs in the signed session cookie.
    session["last_recipe_ids"] = ids
    session.modified = True

    return jsonify({"recipes": recipes})


# ---------------------------------------------------------------------------
# FAVORITES (UNCHANGED)
# ---------------------------------------------------------------------------

















@bp.get("/favorites")
def favorites_page():
    favs = FavoriteRecipe.query.order_by(FavoriteRecipe.created_at.desc()).all()
    return render_template("favorites.html", favorites=[f.to_dict() for f in favs])


@bp.get("/api/favorites")
def api_get_favorites():
    favs = FavoriteRecipe.query.order_by(FavoriteRecipe.created_at.desc()).all()
    return jsonify({"favorites": [f.to_dict() for f in favs]})


@bp.post("/api/favorites")
def api_add_favorite():
    data = request.get_json(silent=True) or {}
    recipe = data.get("recipe")

    if not isinstance(recipe, dict):
        return jsonify({"error": "missing_recipe"}), 400

    recipe_id = str(recipe.get("id") or "").strip()
    title = str(recipe.get("title") or "").strip()

    if not recipe_id or not title:
        return jsonify({"error": "missing_id_or_title"}), 400

    existing = FavoriteRecipe.query.filter_by(id=recipe_id).first()
    if existing:
        return jsonify({"favorite": existing.to_dict(), "created": False})

    fav = FavoriteRecipe(
        id=recipe_id,
        title=title,
        image_url=recipe.get("image_url"),
        payload_json=json.dumps(recipe, ensure_ascii=False),
    )

    db.session.add(fav)
    db.session.commit()

    return jsonify({"favorite": fav.to_dict(), "created": True}), 201


@bp.delete("/api/favorites/<recipe_id>")
def api_delete_favorite(recipe_id: str):
    fav = FavoriteRecipe.query.filter_by(id=recipe_id).first()

    if not fav:
        return jsonify({"error": "not_found"}), 404

    db.session.delete(fav)
    db.session.commit()

    return jsonify({"deleted": True, "id": recipe_id})


# ---------------------------------------------------------------------------
# IMAGE POLLING — frontend polls this until the async SD image is ready
# ---------------------------------------------------------------------------

@bp.get("/api/recipes/image/<recipe_id>")
def api_recipe_image(recipe_id: str):
    """
    Called by the frontend poller every ~1.5 s after the recipes page loads.

    Checks in order:
      1. _IMAGE_CACHE  — populated by the background Together AI thread
      2. _RECIPES_CACHE — in case the recipe already had an image at generation time
      3. _IMAGE_ERRORS  — generation failed; return 200 with null so the frontend stops polling

    Returns:
      200 + {"image": "<data:image/jpeg;base64,...>"}  when ready
      200 + {"image": null, "error": "..."}            when generation permanently failed
      202 + {"image": null}                            while still generating
    """
    # 1. Check the image cache — the background thread writes here when done
    with _CACHE_LOCK:
        image = _IMAGE_CACHE.get(recipe_id)

    # Image is ready — also backfill _RECIPES_CACHE so future page renders show it
    if image:
        recipe = _RECIPES_CACHE.get(recipe_id)
        if recipe is not None and not recipe.get("image"):
            recipe["image"] = image
            recipe["image_url"] = image
        return jsonify({"image": image})

    # 2. Check if a real (non-empty) image was stored at generation time
    recipe = _RECIPES_CACHE.get(recipe_id)
    if recipe:
        stored = recipe.get("image_url") or recipe.get("image") or ""
        if stored:  # only return if genuinely non-empty (not the FALLBACK "")
            return jsonify({"image": stored})

    # 3. Generation permanently failed — tell the frontend to stop polling
    with _CACHE_LOCK:
        error = _IMAGE_ERRORS.get(recipe_id)
    if error is not None:
        print(f"[route] Image error for {recipe_id[:8]}…: {error}")
        return jsonify({"image": None, "error": error})

    # Still generating — tell the frontend to try again
    return jsonify({"image": None}), 202