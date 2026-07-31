from __future__ import annotations

from getpass import getpass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def upsert(lines: list[str], key: str, value: str) -> list[str]:
    prefix = key + "="
    kept = [line for line in lines if not line.startswith(prefix)]
    kept.append(f"{key}={value}")
    return kept


def main() -> int:
    print("EZ AI Album Cover Studio — Gemini setup")
    key = getpass("Paste your Gemini API key, then press ENTER: ").strip()
    if not key:
        print("❌ No Gemini API key was entered.")
        return 1

    existing = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    existing = upsert(existing, "GEMINI_API_KEY", key)
    existing = upsert(existing, "GEMINI_CONCEPT_MODEL", "gemini-3.6-flash")
    existing = upsert(existing, "USE_GEMINI_CREATIVE_DIRECTOR", "true")
    ENV_PATH.write_text("\n".join(existing) + "\n", encoding="utf-8")
    print("✅ Gemini key saved securely in .env")
    print("✅ Gemini 3.6 Flash will enhance/create cover concepts")
    print("✅ OpenAI remains the image renderer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
