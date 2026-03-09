from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import concurrent.futures
import requests
from typing import Any, Dict, List, Optional

from ..utils.prompt_builder import (
    build_recipe_generation_system_prompt,
    build_recipe_generation_user_prompt,
)
from .ingredient_service import normalize_ingredient_list


_IMAGE_CACHE: Dict[str, str] = {}
_IMAGE_ERRORS: Dict[str, str] = {}   # recipe_id -> error message (so we stop retrying)
_CACHE_LOCK = threading.Lock()        # protect both dicts from concurrent writes

FALLBACK_IMAGE = ""

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=6)

# Pexels — free photo search API (200 req/hour, 20,000 req/month)
# Get a free API key at https://www.pexels.com/api/
_PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"


def _pexels_key() -> str:
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        raise RuntimeError("PEXELS_API_KEY environment variable is not set")
    return key


def _build_search_query(title: str, ingredients: List[str]) -> str:
    """Build a focused food search query from the recipe title and ingredients."""
    title = (title or "food dish").strip()

    # Use the title as the primary query — it's the most specific signal.
    # Strip generic cooking words so we get better Pexels results.
    stopwords = {"recipe", "homemade", "easy", "quick", "simple", "classic", "style"}
    words = [w for w in title.lower().split() if w not in stopwords]
    query = " ".join(words).strip() or "food"

    return query


def _fetch_pexels_image(title: str, ingredients: List[str], recipe_id: str) -> str:
    """
    Search Pexels for a food photo matching the recipe title.
    Uses the recipe_id as a deterministic page offset so every recipe
    gets a different photo even when titles are similar.
    Returns a base64 data URL, or FALLBACK_IMAGE on failure.
    """
    with _CACHE_LOCK:
        if recipe_id in _IMAGE_CACHE:
            return _IMAGE_CACHE[recipe_id]
        if recipe_id in _IMAGE_ERRORS:
            return FALLBACK_IMAGE

    try:
        key = _pexels_key()
    except RuntimeError as e:
        print(f"[image] Pexels config error: {e}")
        with _CACHE_LOCK:
            _IMAGE_ERRORS[recipe_id] = str(e)
        return FALLBACK_IMAGE

    query = _build_search_query(title, ingredients)

    # Use recipe_id hash to pick a deterministic page (1–5) so
    # different recipes with similar titles get different photos.
    seed = int(hashlib.sha256(recipe_id.encode()).hexdigest(), 16)
    page = (seed % 5) + 1

    headers = {"Authorization": key}
    params  = {
        "query":       query,
        "per_page":    1,
        "page":        page,
        "orientation": "landscape",
        "size":        "large",
    }

    print(f"[image] Pexels search: '{query}' page={page} (id={recipe_id[:8]}…)")

    try:
        resp = requests.get(_PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)

        if not resp.ok:
            print(f"[image] Pexels HTTP {resp.status_code}: {resp.text[:300]}")
            resp.raise_for_status()

        data   = resp.json()
        photos = data.get("photos") or []

        if not photos:
            # No results for specific title — fall back to generic "food" query
            print(f"[image] Pexels: no results for '{query}', retrying with 'food'")
            params["query"] = "food dish"
            params["page"]  = page
            resp2 = requests.get(_PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
            resp2.raise_for_status()
            photos = resp2.json().get("photos") or []

        if not photos:
            msg = f"no photos found for '{query}'"
            print(f"[image] Pexels: {msg}")
            with _CACHE_LOCK:
                _IMAGE_ERRORS[recipe_id] = msg
            return FALLBACK_IMAGE

        # Prefer large2x > large > original for good quality without huge size
        src      = photos[0].get("src", {})
        img_url  = src.get("large2x") or src.get("large") or src.get("original", "")

        if not img_url:
            msg = "photo had no usable src URL"
            print(f"[image] Pexels: {msg}")
            with _CACHE_LOCK:
                _IMAGE_ERRORS[recipe_id] = msg
            return FALLBACK_IMAGE

        # Download and convert to base64 data URL so it works offline / in iframes
        img_resp = requests.get(img_url, timeout=20)
        img_resp.raise_for_status()
        content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
        encoded  = base64.b64encode(img_resp.content).decode("utf-8")
        data_url = f"data:{content_type};base64,{encoded}"

        with _CACHE_LOCK:
            _IMAGE_CACHE[recipe_id] = data_url

        photographer = photos[0].get("photographer", "")
        print(f"[image] Ready: {recipe_id[:8]}… ({len(data_url) // 1024} KB) — photo by {photographer}")
        return data_url

    except Exception as exc:
        print(f"[image] Pexels error for {recipe_id[:8]}…: {exc}")
        with _CACHE_LOCK:
            _IMAGE_ERRORS[recipe_id] = str(exc)
        return FALLBACK_IMAGE


# Keep the public name consistent with the rest of the module
_generate_image = _fetch_pexels_image


def _recipe_id(title: str, ingredients: List[str]) -> str:
    h = hashlib.sha256()
    h.update((title or "").strip().lower().encode())
    h.update(b"|")
    h.update(",".join(sorted(ingredients or [])).encode())
    return h.hexdigest()[:20]


def ingredient_match_score(recipe_ingredients: List[str], available: List[str]) -> int:
    provided = set(normalize_ingredient_list(available))
    rec = set(normalize_ingredient_list(recipe_ingredients))
    if not provided:
        return 0
    return int(round(100 * len(provided & rec) / len(provided)))


def attach_image_url(recipe: Dict[str, Any], *, async_generate: bool = True) -> Dict[str, Any]:
    """
    Attach an image to the recipe dict via Together AI.
    async_generate=True: returns immediately, generates in background.
    async_generate=False: blocks until image is ready.
    """
    title = recipe.get("title", "")
    ingredients = recipe.get("ingredients") or []
    normalized_ingredients = normalize_ingredient_list(ingredients)
    recipe["ingredients"] = normalized_ingredients

    recipe_id = recipe.get("id")
    if not recipe_id:
        recipe_id = _recipe_id(title, normalized_ingredients)
        recipe["id"] = recipe_id

    with _CACHE_LOCK:
        cached = _IMAGE_CACHE.get(recipe_id)

    if cached:
        recipe["image"] = cached
        recipe["image_url"] = cached
        return recipe

    if async_generate:
        recipe["image"] = FALLBACK_IMAGE
        recipe["image_url"] = FALLBACK_IMAGE

        # Capture variables explicitly to avoid closure-over-loop bugs
        def _bg(_title=title, _ingr=normalized_ingredients, _id=recipe_id):
            _generate_image(_title, _ingr, _id)

        _EXECUTOR.submit(_bg)
    else:
        img = _generate_image(title, normalized_ingredients, recipe_id)
        recipe["image"] = img
        recipe["image_url"] = img

    return recipe


def image_status(recipe_id: str) -> dict:
    """
    Returns a dict with 'status' ('ready' | 'pending' | 'error') and optionally 'image'.
    Useful for polling endpoints to expose meaningful state.
    """
    with _CACHE_LOCK:
        if recipe_id in _IMAGE_CACHE:
            return {"status": "ready", "image": _IMAGE_CACHE[recipe_id]}
        if recipe_id in _IMAGE_ERRORS:
            return {"status": "error", "error": _IMAGE_ERRORS[recipe_id]}
    return {"status": "pending"}


class RecipeService:

    def __init__(self, *, groq):
        self.groq = groq

    def generate_recipes(self, *, ingredients: List[str], count: int = 6, async_images: bool = True):
        ingredients = normalize_ingredient_list(ingredients)
        if not ingredients:
            return []

        try:
            system = build_recipe_generation_system_prompt()
            user = build_recipe_generation_user_prompt(ingredients=ingredients, count=count)
            result = self.groq.chat_json(system=system, user=user).content
            recipes = result.get("recipes", [])
        except Exception as exc:
            print(f"[recipe] Groq generation failed, falling back to local: {exc}")
            return self.generate_recipes_local(
                ingredients=ingredients, count=count, async_images=async_images
            )

        output: List[Dict[str, Any]] = []
        for r in recipes:
            r["ingredients"] = normalize_ingredient_list(r.get("ingredients", []))
            r["id"] = _recipe_id(r.get("title", ""), r["ingredients"])
            attach_image_url(r, async_generate=async_images)
            r["match_score"] = ingredient_match_score(r["ingredients"], ingredients)
            output.append(r)

        output.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return output

    def generate_recipes_local(self, *, ingredients: List[str], count: int = 6, async_images: bool = True):
        main = ingredients[0].title() if ingredients else "Food"
        recipe: Dict[str, Any] = {
            "title": f"{main} Recipe",
            "description": "Generated locally.",
            "ingredients": ingredients,
            "steps": ["Prepare ingredients.", "Cook thoroughly.", "Serve and enjoy."],
            "cooking_time": "20 minutes",
            "difficulty": "Easy",
            "servings": 2,
        }
        recipe["id"] = _recipe_id(recipe["title"], ingredients)
        attach_image_url(recipe, async_generate=async_images)
        recipe["match_score"] = 100
        return [recipe]

    def get_cached_image(self, recipe_id: str) -> Optional[str]:
        with _CACHE_LOCK:
            return _IMAGE_CACHE.get(recipe_id)

    def get_image_status(self, recipe_id: str) -> dict:
        """Expose image_status for use in route handlers."""
        return image_status(recipe_id)

    def serialize_recipe(self, recipe: Dict[str, Any]) -> str:
        return json.dumps(recipe, ensure_ascii=False)