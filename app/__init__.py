from flask import Flask
import os

def create_app():
    app = Flask(__name__)

    # Load configuration from environment variables
    app.config['SPOTIPY_CLIENT_ID'] = os.getenv('SPOTIPY_CLIENT_ID')
    app.config['SPOTIPY_CLIENT_SECRET'] = os.getenv('SPOTIPY_CLIENT_SECRET')
    app.config['SPOTIPY_REDIRECT_URI'] = os.getenv('SPOTIPY_REDIRECT_URI')

    # Import and register blueprints
    from .views.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app

app = create_app()