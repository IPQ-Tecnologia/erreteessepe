try:
    from .app import app, create_app
except ImportError:
    from back.app import app, create_app

__all__ = ["app", "create_app"]
