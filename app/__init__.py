from flask import Flask

from .config import AppConfig
from .models.db import db, migrate


def create_app(config_object: type[AppConfig] = AppConfig) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)
    # Ensure models are registered for migrations
    from . import models  # noqa: F401
    with app.app_context():
        db.create_all()

    from .routes.main_routes import bp as main_bp
    from .routes.recipe_routes import bp as recipe_bp
    from .routes.pantry_routes import bp as pantry_bp
    from .routes.chat_routes import bp as chat_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(recipe_bp)
    app.register_blueprint(pantry_bp)
    app.register_blueprint(chat_bp)

    return app

