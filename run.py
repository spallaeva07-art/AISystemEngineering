
from dotenv import load_dotenv
load_dotenv()  # must run before importing modules that read env vars

from app import create_app
import os

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5051))
    app.run(host="127.0.0.1", port=port, debug=True)