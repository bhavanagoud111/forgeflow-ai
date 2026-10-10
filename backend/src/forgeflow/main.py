"""ASGI entry point: ``uvicorn forgeflow.main:app``."""

from forgeflow.api.app import create_app

app = create_app()
