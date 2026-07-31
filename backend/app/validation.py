from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from fastapi import HTTPException, UploadFile, status


_ALLOWED_MP3_MIME = {"audio/mpeg", "audio/mp3", "audio/x-mp3", "application/octet-stream"}
_ALLOWED_TEXT_MIME = {"text/plain", "application/octet-stream"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_mp3_bytes(data: bytes) -> bool:
    if data.startswith(b"ID3"):
        return True
    # MPEG audio frame sync. Scan a small prefix because ID3-less files can start with metadata.
    prefix = data[:4096]
    return any(
        prefix[i] == 0xFF and (prefix[i + 1] & 0xE0) == 0xE0
        for i in range(max(0, len(prefix) - 1))
    )


async def read_validated_mp3(upload: UploadFile, max_bytes: int) -> bytes:
    suffix = Path(upload.filename or "").suffix.lower()
    content_type = (upload.content_type or "application/octet-stream").lower()
    if suffix != ".mp3" or content_type not in _ALLOWED_MP3_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Audio must be an MP3 file.",
        )
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"MP3 exceeds the configured {max_bytes // (1024 * 1024)} MB limit.",
        )
    if not data or not is_mp3_bytes(data):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded file does not contain a valid MP3 signature.",
        )
    return data


def sanitize_lyrics(text: str, max_chars: int) -> str:
    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        ch for ch in normalized if ch in "\n\t" or unicodedata.category(ch)[0] != "C"
    )
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{4,}", "\n\n\n", normalized).strip()
    if len(normalized) > max_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Lyrics exceed the configured {max_chars:,} character limit.",
        )
    return normalized


async def read_lyrics_file(upload: UploadFile, max_chars: int) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    content_type = (upload.content_type or "application/octet-stream").lower()
    if suffix not in {".txt", ""} or content_type not in _ALLOWED_TEXT_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Lyrics uploads must be UTF-8 plain-text files.",
        )
    raw = await upload.read(max_chars * 4 + 4)
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Lyrics file must be UTF-8 encoded plain text.",
        ) from exc
    return sanitize_lyrics(decoded, max_chars)


def build_input_hash(audio_hash: str | None, lyrics_hash: str | None) -> str:
    canonical = f"audio:{audio_hash or '-'}|lyrics:{lyrics_hash or '-'}".encode("utf-8")
    return sha256_bytes(canonical)
