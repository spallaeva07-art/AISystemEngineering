/* global window, document, fetch */

const $ = (sel) => document.querySelector(sel);
const el = (tag, attrs = {}, children = []) => {
  const n = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  });
  children.forEach((c) => n.appendChild(c));
  return n;
};

function buildDishImageQuery(title, ingredients) {
  const t = (title || "").trim();
  const ings = Array.isArray(ingredients) ? ingredients : [];
  const topIngs = ings.slice(0, 3);

  const lower = t.toLowerCase();
  let dishHint = "";
  if (lower.includes("soup")) dishHint = "bowl of soup";
  else if (lower.includes("stew")) dishHint = "stew in bowl";
  else if (lower.includes("salad")) dishHint = "salad in bowl";
  else if (lower.includes("pizza")) dishHint = "whole pizza";
  else if (lower.includes("burger") || lower.includes("cheeseburger")) dishHint = "burger on plate";
  else if (lower.includes("sandwich") || lower.includes("wrap")) dishHint = "sandwich on plate";
  else if (lower.includes("pasta") || lower.includes("spaghetti")) dishHint = "pasta on plate";
  else if (lower.includes("curry")) dishHint = "curry in bowl";
  else if (lower.includes("dessert")) dishHint = "dessert on plate";
  else if (["cake", "brownie", "cookie", "tart", "pie"].some((w) => lower.includes(w))) dishHint = "dessert";

  const parts = [];
  if (t) parts.push(t);
  if (dishHint) parts.push(dishHint);
  if (topIngs.length) parts.push(topIngs.join(" "));

  const query = parts.join(" ").trim();
  return query || "food";
}

function recipeImageUrl(recipe, index) {
  const primary = (recipe && (recipe.image_url || recipe.image)) || "";
  if (primary) return primary;

  const title = (recipe && recipe.title) || "food";
  const ingredients = Array.isArray(recipe && recipe.ingredients) ? recipe.ingredients : [];
  const query = buildDishImageQuery(title, ingredients);

  const sig =
    (recipe && recipe.id) != null
      ? String(recipe.id)
      : index != null
      ? String(index)
      : Math.random().toString(36).slice(2);

  return `https://source.unsplash.com/900x700/?${encodeURIComponent(query)}&sig=${encodeURIComponent(sig)}`;
}

function recipeImageFallbackUrl(recipe, index) {
  const title = (recipe && recipe.title) || "food";
  const ingredients = Array.isArray(recipe && recipe.ingredients) ? recipe.ingredients : [];
  const query = buildDishImageQuery(title, ingredients);

  const sigBase =
    (recipe && recipe.id) != null
      ? String(recipe.id)
      : index != null
      ? String(index)
      : Math.random().toString(36).slice(2);

  return (
    `https://source.unsplash.com/900x700/?${encodeURIComponent(query)}` +
    `&sig=${encodeURIComponent(sigBase + "-fallback")}&t=${Date.now()}`
  );
}

/**
 * Poll /api/recipes/image/<id> for recipes whose SD image isn't ready yet.
 */
function pollForImages(recipes, imgMap, interval = 1500, maxTries = 20) {
  const pending = new Map(
    recipes
      .filter((r) => r.id && !(r.image_url || r.image))
      .map((r) => [r.id, 0])
  );

  if (!pending.size) return;

  const tick = async () => {
    const done = [];

    await Promise.all(
      [...pending.entries()].map(async ([id, tries]) => {
        if (tries >= maxTries) { done.push(id); return; }
        try {
          const res = await fetch(`/api/recipes/image/${encodeURIComponent(id)}`);
          const data = await res.json().catch(() => null);
          if (!data) { pending.set(id, tries + 1); return; }

          if (data.image) {
            const imgEl = imgMap[id];
            if (imgEl) {
              imgEl.src = data.image;
              imgEl.dataset.fallback = "";
            }
            done.push(id);
          } else if (data.error) {
            // Permanent failure — stop polling
            console.warn("[image] Generation failed for", id, ":", data.error);
            done.push(id);
          } else {
            // Still generating (202)
            pending.set(id, tries + 1);
          }
        } catch (_) { pending.set(id, tries + 1); }
      })
    );

    done.forEach((id) => pending.delete(id));
    if (pending.size > 0) setTimeout(tick, interval);
  };

  setTimeout(tick, interval);
}

// ─── FIX 4: Centralised apiJson used by both app.html inline script and this file ───
// This definition is also present in base.html as a global, but we keep it here
// as a module-level fallback so app.js functions can call it directly.
// base.html defines window.apiJson; here we only define if not already defined.
if (typeof window !== "undefined" && typeof window.apiJson !== "function") {
  window.apiJson = async function apiJson(url, { method = "GET", body, isForm = false } = {}) {
    const opts = { method, credentials: "same-origin", headers: {} };
    if (body) {
      if (isForm) opts.body = body;
      else {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
    }
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data?.error || `request_failed_${res.status}`;
      const err = new Error(msg);
      err.data = data;
      throw err;
    }
    return data;
  };
}

// Keep module-level alias so functions below can call apiJson directly
const apiJson = (...args) => window.apiJson(...args);

function parseTimeMinutes(s) {
  if (!s) return null;
  const m = String(s).match(/(\d+)\s*(min|minute|minutes|hour|hours|hr)/i);
  if (!m) return null;
  const n = Number(m[1]);
  const unit = m[2].toLowerCase();
  if (unit.startsWith("hour") || unit === "hr") return n * 60;
  return n;
}

function renderChips(container, items, { onRemove } = {}) {
  container.innerHTML = "";
  items.forEach((name) => {
    const wrap = el("div", { class: "chip" }, [
      el("span", { text: name }),
      el("button", {
        type: "button",
        class: "ml-1",
        "aria-label": `Remove ${name}`,
        onclick: () => onRemove?.(name),
      }, [document.createTextNode("×")]),
    ]);
    container.appendChild(wrap);
  });
}

function toast(msg, kind = "info") {
  const t = el("div", {
    class:
      "fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-full border px-4 py-2 text-sm font-semibold shadow-lg " +
      (kind === "error"
        ? "border-rose-200 bg-rose-50 text-rose-700"
        : kind === "success"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : "border-slate-200 bg-white text-slate-700"),
    text: msg,
  });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

// ─────────────────────────────────────────────────────────────────────────────
// FIX 1 & 2: initAppPage is REMOVED.
//
// app.html contains its own self-contained inline <script> block that handles:
//   • file input / drag-and-drop (Fix 1 — openPicker() called on click + keydown)
//   • manual ingredient capture and generate() (Fix 2)
//   • pantry management
//   • summary card
//
// Previously, initAppPage() here duplicated that logic but referenced different
// DOM ids (e.g. #browseBtn, #detectBtn that don't exist in app.html), causing:
//   1. fileInput.click() never firing reliably because two competing listeners
//      raced and the secondary one prevented the default browser dialog.
//   2. genManualBtn's setLoading() looked for ".btn-label" inside the button but
//      app.html uses id="spinnerManual" — the label text was never reset, leaving
//      the button stuck in "Working…" forever.
//
// Resolution: the single source of truth for /app page behaviour is the inline
// script in app.html. initAppPage() here is intentionally left as a no-op so
// DOMContentLoaded does not register a second set of conflicting listeners.
// ─────────────────────────────────────────────────────────────────────────────
function initAppPage() {
  // Intentionally empty — /app page behaviour lives in app.html inline script.
  // See app.html {% block scripts %} for the authoritative implementation.
}

// -----------------------
// /recipes page
// -----------------------
function initRecipesPage() {
  const grid = $("#recipesGrid");
  const applyBtn = $("#applyFiltersBtn");
  if (!grid) return;

  let recipes = Array.isArray(window.__RECIPES__) ? window.__RECIPES__ : [];

  const imgMap = {};

  const render = () => {
    grid.innerHTML = "";
    Object.keys(imgMap).forEach((k) => delete imgMap[k]);

    const empty = $("#emptyRecipes");
    if (!recipes.length) { empty && empty.classList.remove("hidden"); return; }
    empty && empty.classList.add("hidden");

    recipes.forEach((r, idx) => {
      const imgEl = el("img", {
        src: recipeImageUrl(r, idx),
        alt: r.title,
        class: "h-44 w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]",
        onerror: function (e) {
          if (e.target.dataset.fallback) return;
          e.target.dataset.fallback = "1";
          e.target.src = recipeImageFallbackUrl(r, idx);
        },
      });

      if (r.id) imgMap[r.id] = imgEl;

      const card = el("div", { class: "card overflow-hidden group" }, [
        el("div", { class: "relative overflow-hidden" }, [
          imgEl,
          el("div", { class: "absolute left-3 top-3 flex gap-2" }, [
            el("span", { class: "pill pill-dark", text: r.difficulty }),
            el("span", { class: "pill pill-dark", text: `Match ${r.match_score ?? 0}%` }),
          ]),
        ]),
        el("div", { class: "p-4" }, [
          el("div", { class: "flex items-start justify-between gap-3" }, [
            el("div", { class: "font-bold text-slate-900", text: r.title }),
            el("button", {
              type: "button",
              class: "text-slate-400 hover:text-warm-600 transition-colors",
              title: "Save to favorites",
              "aria-label": "Save to favorites",
              onclick: async () => {
                try { await apiJson("/api/favorites", { method: "POST", body: { recipe: r } }); toast("Saved to favorites", "success"); }
                catch (e) { toast(e.message, "error"); }
              },
            }, [document.createTextNode("♡")]),
          ]),
          el("div", { class: "mt-1 text-sm text-slate-600", text: r.description }),
          el("div", { class: "mt-3 flex flex-wrap gap-2" }, [
            el("span", { class: "pill", text: `⏱ ${r.cooking_time}` }),
            el("span", { class: "pill", text: `🍽 ${r.servings}` }),
          ]),
          el("div", { class: "mt-4 flex gap-2" }, [
            el("a", { class: "btn btn-primary w-full", href: `/recipe/${encodeURIComponent(r.id)}`, text: "View Recipe" }),
          ]),
        ]),
      ]);
      grid.appendChild(card);
    });

    pollForImages(recipes, imgMap);
  };

  const apply = () => {
    const diff = $("#filterDifficulty")?.value || "";
    const maxTime = $("#filterTime")?.value ? Number($("#filterTime").value) : null;
    const sortBy = $("#sortBy")?.value || "match_desc";

    let filtered = Array.isArray(window.__RECIPES__) ? [...window.__RECIPES__] : [];
    if (diff) filtered = filtered.filter((r) => String(r.difficulty) === diff);
    if (maxTime != null) filtered = filtered.filter((r) => { const m = parseTimeMinutes(r.cooking_time); return m == null ? true : m <= maxTime; });
    if (sortBy === "match_desc") filtered.sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0));
    if (sortBy === "time_asc") filtered.sort((a, b) => (parseTimeMinutes(a.cooking_time) ?? 9999) - (parseTimeMinutes(b.cooking_time) ?? 9999));
    if (sortBy === "title_asc") filtered.sort((a, b) => String(a.title).localeCompare(String(b.title)));

    recipes = filtered;
    render();
  };

  applyBtn?.addEventListener("click", apply);
  apply();
}

// -----------------------
// /recipe/<id> page
// -----------------------
function initRecipeDetailPage() {
  const recipe = window.__RECIPE__;
  if (!recipe || !recipe.id) return;

  const heroImg = document.getElementById("heroImg");
  if (!heroImg) return;

  const currentSrc = heroImg.getAttribute("src") || "";
  if (currentSrc.startsWith("data:")) return;

  let tries = 0;
  const MAX_TRIES = 30;

  const poll = () => {
    if (tries >= MAX_TRIES) return;
    tries++;
    fetch(`/api/recipes/image/${encodeURIComponent(recipe.id)}`)
      .then((r) => r.json().catch(() => null))
      .then((data) => {
        if (!data) { setTimeout(poll, 1500); return; }
        if (data.image) {
          heroImg.src = data.image;
          heroImg.dataset.fb = "";
        } else if (data.error) {
          console.warn("[image] Detail page image failed:", data.error);
          // leave the Unsplash fallback in place
        } else {
          setTimeout(poll, 1500);
        }
      })
      .catch(() => setTimeout(poll, 1500));
  };

  setTimeout(poll, 800);
}

// -----------------------
// /favorites page
// -----------------------
function initFavoritesPage() {
  const grid = $("#favoritesGrid");
  if (!grid) return;

  grid.querySelectorAll("[data-fav-remove]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.favRemove;
      const card = btn.closest("article");
      try {
        await apiJson(`/api/favorites/${encodeURIComponent(id)}`, { method: "DELETE" });
        toast("Removed from favourites", "success");
        if (card) {
          card.style.opacity = "0";
          card.style.transform = "scale(.95)";
          card.style.transition = "all .2s";
          setTimeout(() => card.remove(), 200);
        }
      } catch (e) { toast(e.message, "error"); }
    });
  });

  const imgEls = grid.querySelectorAll("img[data-sig]");
  imgEls.forEach((imgEl) => {
    const src = imgEl.getAttribute("src") || "";
    if (src.startsWith("data:")) return;
    const recipeId = imgEl.dataset.sig;
    if (!recipeId) return;
    let tries = 0;
    const MAX = 30;
    const poll = () => {
      if (tries >= MAX) return;
      tries++;
      fetch(`/api/recipes/image/${encodeURIComponent(recipeId)}`)
        .then((r) => r.json().catch(() => null))
        .then((data) => {
          if (!data) { setTimeout(poll, 1500); return; }
          if (data.image) { imgEl.src = data.image; imgEl.dataset.fb = ""; }
          else if (data.error) { console.warn("[image] Favorites image failed:", data.error); }
          else { setTimeout(poll, 1500); }
        })
        .catch(() => setTimeout(poll, 1500));
    };
    setTimeout(poll, 800);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initAppPage();       // no-op; app.html inline script is authoritative
  initRecipesPage();
  initRecipeDetailPage();
  initFavoritesPage();
});