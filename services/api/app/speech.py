"""Bounded local Whisper transcription. No uploaded audio leaves this host."""

import io
import threading
from functools import lru_cache
from pathlib import Path
from app.config import settings
from app.schemas import DomainError

_transcription = threading.BoundedSemaphore(1)


def available():
    directory = Path(settings().speech_model_directory) / settings().speech_model
    return settings().speech_enabled and (directory / "model.bin").is_file()


@lru_cache(maxsize=1)
def model():
    from faster_whisper import WhisperModel

    return WhisperModel(
        str(Path(settings().speech_model_directory) / settings().speech_model),
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        num_workers=1,
        local_files_only=True,
    )


def transcribe(raw, max_seconds=60):
    if not available():
        raise DomainError(
            "Local voice transcription is unavailable. Type your question or attach a text document instead.",
            503,
        )
    if not _transcription.acquire(blocking=False):
        raise DomainError("Local transcription is busy. Please try again shortly.", 429, retry_after=15)
    try:
        import av
        import numpy as np

        chunks, count = [], 0
        # Decode incrementally: compressed duration metadata cannot bypass the limit.
        with av.open(io.BytesIO(raw)) as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    count += converted.samples
                    if count > max_seconds * 16000:
                        raise DomainError(f"Audio must be no longer than {max_seconds} seconds", 422)
                    chunks.append(converted.to_ndarray().flatten())
            for converted in resampler.resample(None):
                count += converted.samples
                if count > max_seconds * 16000:
                    raise DomainError(f"Audio must be no longer than {max_seconds} seconds", 422)
                chunks.append(converted.to_ndarray().flatten())
        if not count:
            raise DomainError("No readable audio was found", 422)
        audio = np.concatenate(chunks).astype(np.float32) / 32768
        segments, _ = model().transcribe(
            audio, language="en", beam_size=1, vad_filter=True, condition_on_previous_text=False
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise DomainError("No speech was detected. Please try again or type your question", 422)
        return {
            "text": text,
            "duration_seconds": round(count / 16000, 2),
            "method": "local_whisper",
            "language": "en",
            "notice": "Transcribed locally. Review the transcript before sending; original audio is not retained.",
        }
    except DomainError:
        raise
    except Exception:
        raise DomainError(
            "This audio could not be transcribed. Try a clear MP3, WAV, M4A or WebM recording", 422
        )
    finally:
        _transcription.release()
