"""`python -m noctusai_lib.integrations.transcription.server` — container entrypoint."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    from noctusai_lib.integrations.transcription.server.app import create_app
    from noctusai_lib.integrations.transcription.server.engine import FasterWhisperEngine

    model_path = os.environ.get("TRANSCRIBER_MODEL_PATH", "/models/large-v3-turbo")
    app = create_app(FasterWhisperEngine(model_path))
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9000")), workers=1)


if __name__ == "__main__":
    main()
