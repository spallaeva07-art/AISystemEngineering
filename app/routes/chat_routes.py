from __future__ import annotations

import os
from flask import Blueprint, current_app, jsonify, request

from ..services.groq_service import GroqService
from ..utils.prompt_builder import build_chat_system_prompt, build_chat_user_prompt

bp = Blueprint("chat", __name__)

# ── FIELDS STRIPPED FROM RECIPE BEFORE SENDING TO GROQ ────────────────────────
# The frontend sends the full recipe object including large base64 image strings
# (image / image_url). Stripping them before building prompts keeps every chat
# request small (~1 KB instead of ~30 KB) and avoids Pydantic validation issues.
_RECIPE_FIELDS_TO_STRIP = {"image", "image_url"}


def _groq() -> GroqService:
    api_key = current_app.config.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    return GroqService(
        api_key=api_key,
        base_url=current_app.config.get("GROQ_BASE_URL") or "https://api.groq.com/openai/v1",
        model=current_app.config.get("GROQ_MODEL") or "llama-3.3-70b-versatile",
        timeout_s=int(current_app.config.get("GROQ_TIMEOUT_SECONDS") or 60),
    )


def _clean_recipe(obj) -> dict:
    """
    Return a plain dict with only the fields the prompt builder needs.

    Accepts any of: plain dict, Pydantic v1/v2 model, or anything dict()-able.
    Strips image/image_url to keep the request payload small and avoid
    Pydantic schema validation failures when those fields are unexpected.
    """
    if hasattr(obj, "model_dump"):      # Pydantic v2
        raw = obj.model_dump()
    elif hasattr(obj, "dict"):          # Pydantic v1
        raw = obj.dict()
    elif isinstance(obj, dict):
        raw = obj
    else:
        try:
            raw = dict(obj)
        except (TypeError, ValueError):
            raw = {}

    return {k: v for k, v in raw.items() if k not in _RECIPE_FIELDS_TO_STRIP}


@bp.post("/api/chat-recipe")
def api_chat_recipe():
    """
    AI Chef chat endpoint.

    Parses the request body directly — no validate_model() call — so the route
    works regardless of what ChatRecipeRequest looks like in validators.py.
    The validators import has been removed entirely to eliminate that as a
    failure point.

    Expected JSON body: { "recipe": {...}, "message": "user question" }
    Returns JSON:       { "answer": "...", "suggested_questions": ["Q1", ...] }
    """
    data = request.get_json(silent=True) or {}

    # ── Extract and validate inputs directly ──────────────────────────────────
    recipe_raw = data.get("recipe")
    message    = str(data.get("message") or "").strip()

    if not message:
        return jsonify({
            "answer": "Please type a question for the AI Chef.",
            "suggested_questions": [
                "What can I substitute for butter?",
                "How do I know when it's done?",
                "Can I make this spicier?",
            ],
        })

    # Clean the recipe: plain dict, no image blobs
    recipe_dict = _clean_recipe(recipe_raw) if recipe_raw else {}

    # ── Build prompts ─────────────────────────────────────────────────────────
    system = build_chat_system_prompt(recipe=recipe_dict)
    user   = build_chat_user_prompt(recipe=recipe_dict, message=message)

    # ── Call Groq ─────────────────────────────────────────────────────────────
    try:
        parsed = _groq().chat_json(system=system, user=user).content

        answer    = parsed.get("answer") or parsed.get("Answer") or ""
        suggested = parsed.get("suggested_questions") or parsed.get("suggestedQuestions") or []

        if not isinstance(suggested, list):
            suggested = []

        return jsonify({
            "answer": answer or "I'm not sure. Try asking about substitutions or timing.",
            "suggested_questions": [str(q) for q in suggested[:3]],
        })

    except RuntimeError as e:
        msg = str(e)
        if msg == "missing_groq_api_key":
            hint = "GROQ_API_KEY is not configured. Add it to your .env file and restart the server."
        elif msg == "groq_unauthorized":
            hint = "Your GROQ_API_KEY is invalid or expired. Check console.groq.com and update .env."
        elif msg == "groq_http_error":
            hint = "Groq returned an unexpected error. Please try again in a moment."
        elif msg == "groq_request_failed":
            hint = "Could not reach the Groq API. Check your internet connection and try again."
        else:
            current_app.logger.exception("AI chef unexpected RuntimeError: %s", e)
            hint = "The AI Chef is temporarily unavailable."

        return jsonify({
            "answer": hint,
            "suggested_questions": [
                "What can I substitute for garlic?",
                "How do I know when it's done?",
                "Can I make this spicier?",
            ],
        })

    except Exception as e:
        current_app.logger.exception("AI chef chat error: %s", e)
        return jsonify({
            "answer": "Sorry, the AI Chef hit an unexpected error. Please try again.",
            "suggested_questions": [
                "Can I replace butter with olive oil?",
                "What if I don't have garlic?",
            ],
        })