
# FreshChef

FreshChef is a Flask web app that turns whatever's left in your fridge into actual meals. Snap a photo of your ingredients, type a few things in, or pull from your saved pantry — and the app figures out what you can cook. The idea came from a simple frustration: opening the fridge, having no idea what to make, and ending up ordering takeout instead.



## What it does

**Fridge scan** — Upload a photo of your fridge and the app will identify what's in it. No manual typing needed, just point and shoot.

**Manual input** — Prefer to type? Add ingredients one by one and generate recipes from exactly what you have.

**Smart Pantry** — A place to save the staples you always keep around (olive oil, garlic, pasta, etc.). Pantry items get included automatically when you generate recipes, so you don't have to re-enter them every time.

**AI recipe generator** — Recipes are generated using the Groq API. The app sends your ingredients and gets back structured recipes with titles, steps, cook time, difficulty, and serving size. Results are ranked by how well they match what you actually have.

**Recipe photos** — Each recipe card shows a photo pulled from Pexels, matched to the dish name.

**Cooking mode** — A distraction-free step-by-step view for when you're actually at the stove. Includes optional voice commands via the Web Speech API so you don't have to touch your screen with messy hands.

**Favorites** — Save recipes you like. They live in the database and are there whenever you come back.

**AI Chef chat** — On any recipe page, you can open a chat with an AI assistant that knows the recipe you're looking at. Useful for things like "can I substitute the cream?" or "how do I know when it's done?"



## Getting started

### Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:

```
GROQ_API_KEY=your_groq_key
PEXELS_API_KEY=your_pexels_key
```

- Groq key: [console.groq.com](https://console.groq.com) — free tier available
- Pexels key: [pexels.com/api](https://www.pexels.com/api/) — free, no credit card

Then run:

```bash
python run.py
```

Open [http://localhost:5051](http://localhost:5051) in your browser.



### Docker

```bash
cp .env.example .env   # fill in your keys
docker-compose up --build
```

The app runs on port `5051`.



## Project layout

```
app/
  __init__.py        # app factory and extensions
  config.py          # loads environment variables
  routes/            # URL handlers and API endpoints
  services/          # business logic (Groq, recipes, image handling)
  models/            # SQLAlchemy models (PantryItem, FavoriteRecipe)
  utils/             # prompt builders and request validators
  templates/         # Jinja2 HTML templates
  static/            # CSS and JavaScript
```



## API reference

| Method | Endpoint | What it does |
|--------|----------|--------------|
| `POST` | `/api/detect-ingredients` | Detects ingredients from an uploaded image |
| `POST` | `/api/generate-recipes` | Generates recipes from a list of ingredients |
| `POST` | `/api/chat-recipe` | Chat with the AI chef about a specific recipe |
| `GET` | `/api/pantry` | Returns all saved pantry items |
| `POST` | `/api/pantry` | Adds a pantry item |
| `DELETE` | `/api/pantry/<item>` | Removes a pantry item |
| `GET` | `/api/favorites` | Returns saved favorite recipes |
| `POST` | `/api/favorites` | Saves a recipe to favorites |
| `DELETE` | `/api/favorites/<id>` | Removes a favorite |

### Example — generate recipes

```bash
curl -X POST http://localhost:5051/api/generate-recipes \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "pantry+fridge",
    "manual_ingredients": [],
    "detected_ingredients": ["egg", "tomato"],
    "pantry_ingredients": ["pasta", "cheese"],
    "count": 6
  }'
```

`mode` can be `manual`, `fridge`, `pantry`, or `pantry+fridge`.



## Under the hood

Recipes are generated via the [Groq](https://groq.com) API using `llama-3.3-70b-versatile`. The app sends a structured prompt and enforces JSON output so the response can be parsed reliably into recipe cards.

Images are fetched from [Pexels](https://www.pexels.com) using the recipe title as a search query. This happens asynchronously after the recipes load, so the page doesn't wait on photos.

Everything is stored in SQLite — pantry items, favorites, and uploaded images. The database file lives in a Docker volume so it persists across rebuilds.



## What's next

A few things that would make this genuinely more useful:

- **Nutrition breakdown** — calories, macros, and allergens per recipe
- **Meal planner** — pick recipes for the week and auto-generate a shopping list
- **Expiry tracking** — flag ingredients that are running low or about to go off
- **Better fridge detection** — improve accuracy for cluttered or partially visible items

