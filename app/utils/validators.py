from typing import Any, Literal, Optional, Tuple, Type

from pydantic import BaseModel, Field, ValidationError


class ApiError(BaseModel):
    error: str
    details: Optional[Any] = None


class DetectIngredientsResponse(BaseModel):
    ingredients: list[str]


class GenerateRecipesRequest(BaseModel):
    manual_ingredients: list[str] = Field(default_factory=list)
    detected_ingredients: list[str] = Field(default_factory=list)
    pantry_ingredients: list[str] = Field(default_factory=list)
    mode: Literal["manual", "fridge", "pantry", "pantry+fridge"] = "manual"
    count: int = Field(default=6, ge=1, le=12)


class RecipeJson(BaseModel):
    title: str
    description: str
    ingredients: list[str]
    steps: list[str]
    cooking_time: str
    difficulty: str
    servings: int
    tips: list[str] = Field(default_factory=list)
    substitutions: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None


class GenerateRecipesResponse(BaseModel):
    recipes: list[dict]


class ChatRecipeRequest(BaseModel):
    recipe: dict
    message: str = Field(min_length=1, max_length=2000)


class ChatRecipeResponse(BaseModel):
    answer: str
    suggested_questions: list[str] = Field(default_factory=list)


def validate_model(
    model_cls: Type[BaseModel], payload: dict
) -> Tuple[Optional[BaseModel], Optional[ApiError]]:
    try:
        return model_cls.model_validate(payload), None
    except ValidationError as e:
        return None, ApiError(error="validation_error", details=e.errors())

