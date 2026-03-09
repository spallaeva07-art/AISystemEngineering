from __future__ import annotations
import re

_WHITESPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^a-z0-9\s\-]")

def normalize_ingredient(name: str) -> str:
    s = (name or "").strip().lower()
    s = _NON_WORD_RE.sub("", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()

    if s.endswith("ies") and len(s) > 4:
        s = s[:-3] + "y"
    elif s.endswith("oes") and len(s) > 4:
        s = s[:-2]
    elif s.endswith("s") and not s.endswith(("ss", "us", "is")) and len(s) > 3:
        s = s[:-1]

    return s

class Pantry:
    def __init__(self, items: list[str] | None = None):
        self.items: set[str] = set(normalize_ingredient_list(items or []))

    def add_item(self, name: str) -> None:
        n = normalize_ingredient(name)
        if n:
            self.items.add(n)

    def remove_item(self, name: str) -> None:
        n = normalize_ingredient(name)
        self.items.discard(n)

    def is_staple(self, name: str) -> bool:
        return normalize_ingredient(name) in self.items


def normalize_ingredient_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items or []:
        n = normalize_ingredient(it)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out

# Common cooking staples that are present in virtually every kitchen.
# Used when no explicit Pantry object is supplied.
_DEFAULT_STAPLES: frozenset[str] = frozenset({
    "salt", "pepper", "oil", "olive oil", "vegetable oil", "canola oil",
    "water", "sugar", "brown sugar", "flour", "all-purpose flour",
    "butter", "baking soda", "baking powder", "vinegar", "soy sauce",
    "black pepper", "white pepper", "garlic powder", "onion powder",
    "paprika", "cumin", "cinnamon", "oregano", "thyme", "bay leaf",
    "cornstarch", "cooking spray",
})


def filter_out_staples(items: list[str], pantry: "Pantry | None" = None) -> list[str]:
    """Return items that are not pantry staples.

    If a Pantry object is supplied uses its ``is_staple()`` method;
    otherwise falls back to the built-in ``_DEFAULT_STAPLES`` set.
    This makes the second argument optional so callers can pass a plain
    list of ingredient strings without constructing a Pantry object first.
    """
    normalized = normalize_ingredient_list(items)
    if pantry is not None:
        return [x for x in normalized if not pantry.is_staple(x)]
    return [x for x in normalized if x not in _DEFAULT_STAPLES]

def parse_ingredient_text(text: str) -> list[str]:
    if not text:
        return []
    raw = re.split(r"[\n,;]+", text)
    return normalize_ingredient_list(raw)