"""Backward-compatible entrypoint for older commands and integrations."""

from app import app, create_app

__all__ = ["app", "create_app"]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)