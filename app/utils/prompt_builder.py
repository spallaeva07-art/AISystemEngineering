from __future__ import annotations


def build_recipe_generation_system_prompt() -> str:
    return """
You are a cooking assistant that creates realistic recipes from available ingredients.
Return JSON only.

Rules:
- Generate multiple DISTINCT recipes.
- Each recipe must feel visually different from the others.
- Prefer natural dish names over vague names.
- Avoid overusing words like: leftover, quick, simple, easy.
- Use the provided ingredients as the base and do not introduce new main ingredients that are not listed by the user.
- You may optionally use only very basic pantry staples (salt, pepper, oil, water, flour, sugar, stock, broth, etc.) as helpers.
- Never invent completely new mains like pasta, rice, or new proteins if they were not listed.

For each recipe, include:
- title
- description
- ingredients
- steps
- cooking_time
- difficulty
- servings
- tips
- substitutions
- image_query

Rules for image_query:
- It must describe the FINISHED DISH visually.
- It must be specific and food-photography friendly.
- Include the actual dish type and 1-3 main ingredients.
- Do NOT use generic queries like:
  "food", "meal", "dish", "recipe", "plated food", "home cooked meal"
- Good examples:
  "brown sugar cookies close up"
  "vegetable quiche slice on plate"
  "crepes with fruit filling"
  "savory pancakes with herbs"
""".strip()


def build_recipe_generation_user_prompt(ingredients: list[str], count: int = 6) -> str:
    joined = ", ".join(ingredients)
    return f"""
Create {count} distinct recipes using ONLY these ingredients as the main components:
{joined}

You may additionally use only very basic pantry staples such as salt, pepper, oil, water, flour, sugar, stock, broth, and similar helpers.
Do NOT add completely new main ingredients (for example: do not invent pasta, rice, or new proteins if they were not in the list).

Return JSON in this shape:
{{
  "recipes": [
    {{
      "title": "string",
      "description": "string",
      "ingredients": ["string"],
      "steps": ["string"],
      "cooking_time": "string",
      "difficulty": "Easy | Medium | Hard",
      "servings": 2,
      "tips": ["string"],
      "substitutions": ["string"],
      "image_query": "specific food photo search query"
    }}
  ]
}}
""".strip()


def build_chat_system_prompt(recipe: dict | None = None) -> str:
    title = ""
    description = ""
    ingredients = []
    steps = []

    if isinstance(recipe, dict):
        title = recipe.get("title", "")
        description = recipe.get("description", "")
        ingredients = recipe.get("ingredients", []) or []
        steps = recipe.get("steps", []) or []

    ingredients_text = ", ".join(str(x) for x in ingredients) if ingredients else "Not provided"
    steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps)) if steps else "Not provided"

    return f"""
You are a helpful cooking assistant answering questions about a specific recipe.

Your job:
- Answer clearly and practically.
- Help with substitutions, cooking tips, texture fixes, serving ideas, storage, reheating, and timing.
- Stay focused on the provided recipe.
- Do not invent irrelevant details.
- If something is uncertain, say so honestly and give the safest useful advice.

You must respond with valid JSON only, in this exact shape (no other text):
{{"answer": "your full reply to the user here", "suggested_questions": ["Follow-up question 1?", "Follow-up question 2?", "Follow-up question 3?"]}}

Recipe title: {title}
Recipe description: {description}
Recipe ingredients: {ingredients_text}
Recipe steps:
{steps_text}
""".strip()


def build_chat_user_prompt(recipe: dict | None = None, message: str = "") -> str:
    # BUG FIX 3: The previous implementation re-sent the full recipe (title,
    # description, ingredients, steps) in BOTH the system turn AND the user turn.
    # That duplication caused two problems:
    #   a) Token waste on every request.
    #   b) Some models treat contradictory/repeated context as a signal to hedge,
    #      producing vague answers rather than recipe-specific ones.
    #
    # The recipe context is already fully embedded in the system prompt by
    # build_chat_system_prompt(recipe=...). The user turn should contain only
    # the user's question so the model's attention stays on answering it.
    return (message or "").strip()