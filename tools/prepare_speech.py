"""Download public speech weights once; requests never download models or send audio."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/api"))
from app.config import settings  # noqa: E402
from faster_whisper.utils import download_model  # noqa: E402


def main():
    configuration = settings()
    if configuration.speech_model not in {"tiny.en", "base.en", "small.en"}:
        raise SystemExit("Choose a supported local English model: tiny.en, base.en or small.en")
    target = Path(configuration.speech_model_directory) / configuration.speech_model
    target.mkdir(parents=True, exist_ok=True)
    if not (target / "model.bin").is_file():
        download_model(configuration.speech_model, output_dir=str(target), use_auth_token=False)
    from app.speech import model

    model()
    print(f"Local CPU transcription prepared: {configuration.speech_model}. Audio stays on this host.")


if __name__ == "__main__":
    main()
