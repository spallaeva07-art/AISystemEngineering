from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
from pathlib import Path
from typing import List, Optional

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .groq_service import GroqService
from .ingredient_service import normalize_ingredient_list

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_GENERIC_FILENAME_TOKENS = {
    "img", "image", "photo", "pantry", "kitchen", "groceries",
    "grocery", "fridge", "upload", "camera", "snapshot",
}


def _allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def save_upload(file: FileStorage, upload_folder: str) -> str:
    if not file or not file.filename:
        raise ValueError("missing_file")

    filename = secure_filename(file.filename)
    if not filename or not _allowed(filename):
        raise ValueError("unsupported_file_type")

    os.makedirs(upload_folder, exist_ok=True)

    ext = Path(filename).suffix.lower()
    token = secrets.token_hex(12)
    stored = f"fridge_{token}{ext}"
    path = os.path.join(upload_folder, stored)

    file.save(path)
    return path


def detect_ingredients_placeholder(image_path: str) -> List[str]:
    return ["salt", "pepper", "flour", "rice", "tomato", "onion"]


def _looks_like_random_token(token: str) -> bool:
    token = (token or "").strip().lower()
    if not token:
        return True

    if token.isdigit():
        return True

    if re.fullmatch(r"[a-f0-9]{8,}", token):
        return True

    return False


def _fallback_from_filename(image_path: str) -> List[str]:
    filename = os.path.basename(image_path or "")
    if not filename:
        return detect_ingredients_placeholder(image_path)

    name_without_ext, _ = os.path.splitext(filename)
    raw_tokens = re.split(r"[\s_,.-]+", name_without_ext)

    candidates: list[str] = []
    for token in raw_tokens:
        token = (token or "").strip().lower()

        if not token or len(token) < 3 or token in _GENERIC_FILENAME_TOKENS or _looks_like_random_token(token):
            continue

        candidates.append(token)

    cleaned = normalize_ingredient_list(candidates)
    if cleaned:
        return cleaned

    return detect_ingredients_placeholder(image_path)


def _extract_ingredients_from_response(content: dict) -> List[str]:
    raw_ingredients = content.get("ingredients", [])
    if not isinstance(raw_ingredients, list):
        raise ValueError("ingredients is not a list")

    text_items = [item for item in raw_ingredients if isinstance(item, str)]
    cleaned = normalize_ingredient_list(text_items)

    if not cleaned:
        raise ValueError("empty_ingredients")

    # Allow variety of foods including spices, condiments, seafood, dairy, grains, etc.
    return cleaned[:50]  # increased from 25 to 50


def detect_ingredients_with_groq_vision(
    *,
    image_path: str,
    groq: Optional[GroqService] = None,
    vision_model: Optional[str] = None,
) -> List[str]:
    if not image_path or not os.path.isfile(image_path):
        return detect_ingredients_placeholder(image_path)

    if groq is None:
        return _fallback_from_filename(image_path)

    mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    system = (
        "You are an advanced ingredient detection AI for user-uploaded kitchen, pantry, fridge, "
        "and cooked-food photos. You must list every clearly visible edible item, "
        "including all spices, condiments, salts, peppers, seafood, meats, poultry, dairy, eggs, "
        "cheeses, grains, flours, oils, vegetables, fruits, sauces, canned foods, and packaged items. "
        "Always respond with strict JSON only."
    )

    user_text = (
        "Carefully analyze this image and return all edible ingredients you can see. Include:\n"
        "- Fresh produce: fruits, vegetables, leafy greens, herbs\n"
        "- Proteins: meat, poultry, seafood, eggs, tofu, plant-based proteins\n"
        "- Dairy: milk, butter, yogurt, cheeses, cream\n"
        "- Grains: rice, pasta, noodles, bread, flour, cereals\n"
        "- Condiments, sauces, spices: all salts, peppers, seasonings, oils, vinegar, soy sauce, etc.\n"
        "- Packaged foods: cans, jars, boxes, frozen foods (only if clearly visible)\n"
        "Rules:\n"
        "- Only include items that are reasonably visible.\n"
        "- Ignore non-food objects and generic packaging text.\n"
        "- Use singular, lowercase names: 'tomato', 'egg', 'chicken breast', 'black pepper', 'olive oil'.\n"
        "- Return at most 50 items.\n"
        'Return ONLY valid JSON in this format: {"ingredients": ["milk", "egg", "tomato"]}'
    )

    try:
        result = groq.chat_json_with_image(
            system=system,
            user_text=user_text,
            image_bytes=image_bytes,
            image_mime=mime_type,
            model=vision_model,
        )
        return _extract_ingredients_from_response(result.content)
    except (RuntimeError, ValueError, json.JSONDecodeError):
        return _fallback_from_filename(image_path)