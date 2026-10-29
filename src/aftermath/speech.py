"""Speech in and out, with Meta's models.

- Listening on this machine: MMS-1B (facebook/mms-1b-all) through mlx-audio, with the person's language adapter.
  mlx-audio loads the English adapter and vocabulary; other languages are swapped in here. Decoding is greedy CTC
  done once (mlx-audio's own path merges repeated letters twice, turning "llamar" into "lamar").
- Listening through the Meta Model API: Muse Voice Transcribe (``MuseListener``), the same interface.
- Speaking: one MMS-TTS voice per language (facebook/mms-tts-spa, -eng, -hin), through transformers, with the text
  made speakable first (speakable.py).

All MMS weights are CC BY-NC 4.0: fine for the hackathon, not for a product. Out of the box, without a language
model, MMS mishears about 14% of Spanish words (Pratap et al. 2023, Table A1), and it can hear a lone "sí" as "se",
so a short answer that would take a danger off the list must be plain (conversation.py).
"""

import io
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import meta_api
from .cache import ResponseCache, file_digest
from .meta_api import API  # noqa: F401  (where the requests go)

ASR_REPO, ASR_REVISION = "facebook/mms-1b-all", "3d33597edbdaaba14a8e858e2c8caa76e3cec0cd"
ADAPTERS = {"es": "spa", "en": "eng", "hi": "hin"}
ASR_FILES = ["config.json", "model.safetensors", "vocab.json", "tokenizer_config.json", "special_tokens_map.json",
             "preprocessor_config.json"] + [f"adapter.{code}.safetensors" for code in ADAPTERS.values()]
VOICES = {"es": ("facebook/mms-tts-spa", "833b96c0278c85cf09776d565ba8f1cb2819f7ec"),
          "en": ("facebook/mms-tts-eng", "c71de0fe7204c83f1c10820a7d696d0b450048ba"),
          "hi": ("facebook/mms-tts-hin", "1d83b223ec78e30b944f7d96bd117eb3d7023303")}


def ctc_greedy(ids: list[int], vocab: dict[int, str], blank: int = 0) -> str:
    """Greedy CTC decoding: merge runs of the same id once, drop blanks and special tokens; "|" separates words."""
    tokens = [vocab.get(i, "") for i, before in zip(ids, [None, *ids[:-1]]) if i != before and i != blank]
    return "".join(t for t in tokens if not t.startswith("<")).replace("|", " ").strip()


def to_wav16k(source: str | Path, out: str | Path) -> Path:
    """Any audio ffmpeg reads, as 16 kHz mono WAV (what MMS expects)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-ar", "16000", "-ac", "1", str(out)],
                   check=True)
    return Path(out)


def write_wav(path, audio: np.ndarray, rate: int):
    """16-bit mono WAV, to a path or an open binary file."""
    with wave.open(path if hasattr(path, "write") else str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return path if hasattr(path, "write") else Path(path)


class Listener:
    """MMS-1B speech recognition. ``transcribe`` takes a 16 kHz mono WAV and a language ("es" or "en")."""

    def __init__(self, cache: ResponseCache | None = None) -> None:
        self.cache = cache
        self._model, self._path, self._language, self._vocab = None, None, None, None

    def _use(self, language: str) -> None:
        import mlx.core as mx
        import mlx.nn as nn
        from mlx_audio.stt.utils import get_model_path, load

        if self._model is None:
            self._path = Path(get_model_path(ASR_REPO, revision=ASR_REVISION, allow_patterns=ASR_FILES))
            # By repo id: mlx-audio recognises MMS from its name (a local path reads as plain wav2vec2).
            self._model = load(ASR_REPO, revision=ASR_REVISION, allow_patterns=ASR_FILES)
        if self._language != language:
            code = ADAPTERS[language]
            weights = self._model.sanitize(mx.load(str(self._path / f"adapter.{code}.safetensors")))
            self._model.lm_head = nn.Linear(self._model.config.hidden_size, weights["lm_head.weight"].shape[0])
            self._model.load_weights(list(weights.items()), strict=False)
            vocab = json.loads((self._path / "vocab.json").read_text())[code]
            self._vocab, self._language = {index: token for token, index in vocab.items()}, language

    def _decode(self, wav: Path, language: str) -> str:
        import mlx.core as mx
        from mlx_audio.stt.utils import load_audio

        self._use(language)
        audio = load_audio(str(wav), sr=16000)[None, :]
        audio = (audio - mx.mean(audio, axis=-1, keepdims=True)) / (mx.std(audio, axis=-1, keepdims=True) + 1e-7)
        return ctc_greedy(mx.argmax(self._model(audio), axis=-1)[0].tolist(), self._vocab)

    def request(self, wav: str | Path, language: str) -> dict:
        """What names this transcription in the cache."""
        return {"task": "transcribe", "backend": "mlx-audio", "model": ASR_REPO, "revision": ASR_REVISION,
                "adapter": ADAPTERS[language], "decoder": "ctc-greedy-once", "audio": file_digest(wav)}

    def transcribe(self, wav: str | Path, language: str = "es") -> str:
        wav = Path(wav)
        if self.cache is None:
            return self._decode(wav, language)
        return self.cache.fetch(self.request(wav, language), lambda: self._decode(wav, language))["result"]


PUNCTUATION = ".,;:!?।॥\"'«»“”‘’()"


def without_repeats(text: str) -> str:
    """Voice Transcribe sometimes writes a word twice: on Oct 29, given Lekha's voice with half a second of silence
    around each answer, "घर से से दूर", "पेट्रोल का का एक टैंक" and, run together, "नॉर्मलनॉर्मल है" and
    "पेट्रोलपेट्रोल". A word twice in a row is kept once, and so is a word run into itself when each half has at least
    three characters, so that "दादा", "मामा" and "चाचा" stay as they are."""
    kept: list[str] = []
    for token in text.split():
        core = token.rstrip(PUNCTUATION)
        half = len(core) // 2
        if len(core) % 2 == 0 and half >= 3 and core[:half] == core[half:]:
            token = core[:half] + token[len(core):]
        if kept and kept[-1].strip(PUNCTUATION).lower() == token.strip(PUNCTUATION).lower():
            continue
        kept.append(token)
    return " ".join(kept)


TRANSCRIBER = "muse-voice-transcribe-1.0"
LANGUAGE_NAMES = {"es": "Spanish", "en": "English", "hi": "Hindi"}  # how Voice Transcribe's languageBias names them


def bare_wav(path: str | Path, pad_s: float = 0.0) -> bytes:
    """A 16-bit mono WAV as a plain RIFF header and its samples, with ``pad_s`` of silence on each side. ffmpeg adds
    a LIST chunk of metadata, and Voice Transcribe takes only mono 16-bit PCM at 16 or 24 kHz."""
    with wave.open(str(path), "rb") as source:
        params, frames = source.getparams(), source.readframes(source.getnframes())
    if params.nchannels != 1 or params.sampwidth != 2 or params.framerate not in (16000, 24000):
        raise ValueError(f"{path}: Voice Transcribe takes mono 16-bit PCM at 16 or 24 kHz")
    silence = bytes(2 * round(pad_s * params.framerate))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(params.framerate)
        out.writeframes(silence + frames + silence)
    return buffer.getvalue()


class MuseListener:
    """Muse Voice Transcribe through the Meta Model API, with the same ``transcribe(wav, language)`` as ``Listener``.

    The key comes from MODEL_API_KEY (or META_API_KEY). Each recording is one push-to-talk turn, sent with the
    conversation's language as a hint (``hint=False`` lets the model detect it) and ``pad_s`` of silence on each
    side: on Oct 29 a lone "Sí." 0.4 s long came back empty, and heard right with 0.5 s of silence around it. Meta
    bills whole seconds of audio ($0.18 an hour) and offers no contributor tier for it. The API returns no
    confidence.
    """

    def __init__(self, cache: ResponseCache | None = None, hint: bool = True, pad_s: float = 0.5, client=None,
                 retries: int = 2) -> None:
        self.cache, self.hint, self.pad_s, self.retries = cache, hint, pad_s, retries
        self._client = client

    def settings(self, language: str) -> dict:
        settings = {"model": TRANSCRIBER, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
        if self.hint:
            settings["languageBias"] = [LANGUAGE_NAMES[language]]
        return settings

    def _http(self):
        if self._client is None:
            self._client = meta_api.client(timeout=30)
        return self._client

    def _call(self, wav: Path, language: str) -> str:
        files = {"request": (None, json.dumps(self.settings(language)), "application/json"),
                 "audio": ("said.wav", bare_wav(wav, self.pad_s), "audio/wav")}
        response = meta_api.post(self._http(), "/asr/transcribe", self.retries, files=files,
                                 headers={"Accept": "application/json"})
        return response.json()["transcript"].strip()

    def request(self, wav: str | Path, language: str) -> dict:
        """What names this transcription in the cache."""
        return {"task": "transcribe", "backend": "meta-api", **self.settings(language), "pad_s": self.pad_s,
                "audio": file_digest(wav)}

    def transcribe(self, wav: str | Path, language: str = "es") -> str:
        wav = Path(wav)
        if self.cache is None:
            return without_repeats(self._call(wav, language))
        heard = self.cache.fetch(self.request(wav, language), lambda: self._call(wav, language))["result"]
        return without_repeats(heard)  # the cache keeps what the API returned


class Voice:
    """MMS-TTS voices, loaded the first time each language speaks."""

    def __init__(self) -> None:
        self._voices = {}

    def _load(self, language: str):
        if language not in self._voices:
            from transformers import AutoTokenizer, VitsModel

            repo, revision = VOICES[language]
            self._voices[language] = (VitsModel.from_pretrained(repo, revision=revision).eval(),
                                      AutoTokenizer.from_pretrained(repo, revision=revision))
        return self._voices[language]

    def rate(self, language: str) -> int:
        return self._load(language)[0].config.sampling_rate

    def speak(self, text: str, language: str = "es") -> np.ndarray:
        """The text spoken, as float samples at ``rate(language)``: chunk by chunk, as speakable.py cuts it (numbers in
        words, no punctuation), with a short silence after each chunk."""
        import torch

        from .speakable import chunks

        model, tokenizer = self._load(language)
        rate, parts = model.config.sampling_rate, []
        for chunk, pause in chunks(text, language):
            with torch.no_grad():
                parts.append(model(**tokenizer(chunk, return_tensors="pt")).waveform[0].numpy())
            parts.append(np.zeros(round(pause * rate), dtype=np.float32))
        return np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
