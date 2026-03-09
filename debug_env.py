"""
Run inside the container to verify Together AI is reachable and the key works:

  docker exec freshchef_app python debug_env.py
"""
import os
import sys
import requests

TOGETHER_API_URL = "https://api.together.xyz/v1/images/generations"
TOGETHER_MODEL   = "black-forest-labs/FLUX.1-schnell-Free"

key = os.environ.get("TOGETHER_API_KEY", "")
groq_key = os.environ.get("GROQ_API_KEY", "")

print("=" * 55)
print("ENV CHECK")
print("=" * 55)
print(f"TOGETHER_API_KEY : {'SET (' + key[:6] + '…)' if key else '*** NOT SET ***'}")
print(f"GROQ_API_KEY     : {'SET (' + groq_key[:6] + '…)' if groq_key else '*** NOT SET ***'}")
print()

if not key:
    print("FATAL: TOGETHER_API_KEY is missing.")
    print("Add it to your .env file:  TOGETHER_API_KEY=your_key_here")
    print("Get a free key at https://api.together.xyz")
    sys.exit(1)

print("Testing Together AI with a minimal 256x256 request…")
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
payload = {
    "model": TOGETHER_MODEL,
    "prompt": "a plate of pasta, food photography",
    "width":  256,
    "height": 256,
    "steps":  4,
    "n":      1,
}

try:
    resp = requests.post(TOGETHER_API_URL, json=payload, headers=headers, timeout=60)
    print(f"HTTP status : {resp.status_code}")
    data = resp.json()
    if resp.ok:
        images = data.get("data") or []
        if images and images[0].get("url"):
            print(f"SUCCESS — image URL: {images[0]['url'][:80]}…")
        else:
            print(f"Unexpected response shape: {list(data.keys())}")
    else:
        print(f"FAILED — response body: {resp.text[:500]}")
except Exception as e:
    print(f"Request error: {e}")
    print("Check that the container can reach the internet.")

print()
print("Done.")