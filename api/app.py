# api/app.py
# Vercel Python WSGI entrypoint. Exposes a WSGI callable named `app`.
# It imports the Flask app from your package without running a server.

try:
    # Prefer the Flask instance defined in app/main.py
    from app.main import app as app
except Exception:
    # Fallback: if your package uses an application factory, import and call it
    try:
        from app import create_app
        app = create_app()
    except Exception as e:
        # Raise so Vercel build logs show the problem clearly
        raise

# Some runtimes expect `application` as well
application = app
