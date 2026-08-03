from __future__ import annotations

import uvicorn

from knowagent_model.settings import ModelServiceSettings


def main() -> None:
    settings = ModelServiceSettings.from_environment()
    uvicorn.run(
        "knowagent_model.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
