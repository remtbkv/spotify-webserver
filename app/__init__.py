"""app package initializer.

This file intentionally avoids creating a Flask `app` at import time so that
importing submodules (e.g. `app.spotify_client`) doesn't execute application
setup or register blueprints. Use `create_app()` from an entrypoint script if
you need the full application factory behavior.
"""

from importlib import import_module

def create_app():
    """Application factory (call explicitly from an entrypoint).

    Returns a Flask app with blueprints registered.
    """
    from flask import Flask
    import os

    app = Flask(__name__)
    app.config['SPOTIPY_CLIENT_ID'] = os.getenv('SPOTIPY_CLIENT_ID')
    app.config['SPOTIPY_CLIENT_SECRET'] = os.getenv('SPOTIPY_CLIENT_SECRET')
    app.config['SPOTIPY_REDIRECT_URI'] = os.getenv('SPOTIPY_REDIRECT_URI')

    # Lazily import and register blueprints
    try:
        mod = import_module('.views.routes', package=__name__)
        blueprint = getattr(mod, 'routes', None)
        if blueprint:
            app.register_blueprint(blueprint)
    except Exception:
        # If blueprint import fails, allow the caller to handle it.
        pass

    return app