try:
    from .app import app, create_app
except ImportError:  
    from python_webrtc.app import app, create_app

__all__ = ["app", "create_app"]
