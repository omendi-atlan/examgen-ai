"""Process entry point for platform deployment.

PaaS providers (Render, Railway, Heroku, Fly, etc.) invoke a module-level
``app`` object. Configuration is entirely environment driven — see
``examgen/config.py`` for the supported variables.
"""

from __future__ import annotations

from examgen.api.app import create_app

app = create_app()
