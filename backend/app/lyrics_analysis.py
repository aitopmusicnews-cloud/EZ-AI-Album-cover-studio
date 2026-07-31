from __future__ import annotations

from collections import Counter
import math
import re
from typing import Any


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’-]{1,30}")
_STOP_WORDS = {
    "the", "and", "that", "with", "this", "from", "your", "you", "are", "was", "were",
    "have", "has", "had", "for", "not", "but", "all", "can", "our", "out", "into", "when",
    "what", "who", "why", "how", "where", "then", "than", "them", "they", "their", "there",
    "here", "just", "like", "love", "will", "would", "could", "should", "been", "being", "about",
    "over", "under", "again", "more", "some", "such", "only", "very", "too", "also", "its",
    "it's", "i'm", "i've", "i'll", "we're", "don't", "can't", "won't", "ain't", "got", "get",
    "one", "two", "now", "yeah", "oh", "ooh", "la", "na", "verse", "chorus", "bridge",
}

_POSITIVE = {
    "alive", "beautiful", "bright", "celebrate", "dance", "dream", "free", "glory", "golden",
    "good", "happy", "heaven", "hope", "joy", "kiss", "laugh", "light", "lucky", "peace",
    "rise", "shine", "smile", "strong", "sun", "together", "triumph", "warm", "win", "wonder",
}
_NEGATIVE = {
    "alone", "anger", "ashes", "bleed", "broken", "cold", "cry", "dark", "dead", "death",
    "devil", "die", "empty", "fear", "ghost", "grief", "hate", "hurt", "lonely", "lost",
    "nightmare", "pain", "rain", "regret", "sad", "shadow", "sorrow", "tears", "war", "wound",
}
_ACTIVE = {
    "burn", "crash", "dance", "drive", "explode", "fight", "fire", "fly", "jump", "race", "rage",
    "rise", "run", "shout", "slam", "storm", "strike", "thunder", "wild",
}

_EMOTIONS = {
    "joy": {"joy", "happy", "smile", "dance", "celebrate", "bright", "sun", "laugh"},
    "sadness": {"sad", "cry", "tears", "grief", "sorrow", "lonely", "empty", "regret"},
    "anger": {"anger", "rage", "hate", "fight", "burn", "war", "strike", "scream"},
    "fear": {"fear", "afraid", "nightmare", "ghost", "shadow", "dark", "haunt"},
    "romance": {"kiss", "heart", "lover", "romance", "touch", "desire", "darling", "baby"},
    "hope": {"hope", "rise", "dream", "tomorrow", "free", "light", "strong", "heaven"},
    "defiance": {"fight", "stand", "never", "strong", "rebel", "break", "free", "wild"},
}

_THEMES = {
    "love and intimacy": {"heart", "kiss", "lover", "romance", "touch", "desire", "darling", "baby"},
    "loss and memory": {"lost", "gone", "memory", "remember", "goodbye", "grief", "regret", "ghost"},
    "freedom and escape": {"free", "escape", "fly", "road", "drive", "run", "open", "wild"},
    "resilience and rebirth": {"rise", "again", "strong", "survive", "ashes", "reborn", "heal"},
    "nightlife and motion": {"night", "city", "dance", "club", "neon", "street", "lights", "drive"},
    "nature and seasons": {"ocean", "sea", "river", "rain", "sun", "moon", "sky", "forest", "winter"},
    "conflict and defiance": {"fight", "war", "rebel", "rage", "stand", "enemy", "break"},
    "identity and reflection": {"mirror", "name", "self", "inside", "truth", "face", "soul"},
}

_IMAGERY = {
    "ashes", "blood", "bridge", "city", "cloud", "diamond", "door", "fire", "flower", "forest",
    "ghost", "glass", "gold", "heart", "highway", "light", "mirror", "moon", "mountain", "neon",
    "night", "ocean", "rain", "river", "road", "shadow", "sky", "smoke", "star", "storm", "sun",
    "thunder", "train", "tree", "water", "wave", "window", "wing", "winter",
}


class LyricsAnalyzer:
    def analyze(self, text: str) -> dict[str, Any]:
        tokens = [match.group(0).lower().replace("’", "'") for match in _TOKEN_RE.finditer(text)]
        if not tokens:
            return {
                "mood": {"label": "introspective", "valence": 0.0, "energy": 0.3},
                "themes": ["abstract reflection"],
                "tone": ["introspective"],
                "keywords": [],
                "imagery": [],
                "token_count": 0,
            }

        counts = Counter(token for token in tokens if token not in _STOP_WORDS and len(token) >= 3)
        positive = sum(counts[word] for word in _POSITIVE)
        negative = sum(counts[word] for word in _NEGATIVE)
        emotional_total = positive + negative
        valence = (positive - negative) / max(3.0, math.sqrt(len(tokens)) + emotional_total)
        valence = max(-1.0, min(1.0, valence))

        active = sum(counts[word] for word in _ACTIVE)
        punctuation_energy = min(0.25, (text.count("!") + text.count("?") * 0.25) / 20.0)
        energy = min(1.0, 0.22 + active / max(8.0, math.sqrt(len(tokens)) * 2.0) + punctuation_energy)

        emotion_scores = {
            name: sum(counts[word] for word in vocabulary) for name, vocabulary in _EMOTIONS.items()
        }
        tone = [name for name, score in sorted(emotion_scores.items(), key=lambda item: (-item[1], item[0])) if score > 0][:3]
        if not tone:
            tone = [self._mood_label(valence, energy)]

        theme_scores = {
            name: sum(counts[word] for word in vocabulary) for name, vocabulary in _THEMES.items()
        }
        themes = [name for name, score in sorted(theme_scores.items(), key=lambda item: (-item[1], item[0])) if score > 0][:4]
        if not themes:
            themes = ["personal reflection"]

        keywords = [word for word, _ in counts.most_common(12)]
        imagery = [word for word in keywords if word in _IMAGERY][:8]
        return {
            "mood": {
                "label": self._mood_label(valence, energy),
                "valence": round(valence, 4),
                "energy": round(energy, 4),
            },
            "themes": themes,
            "tone": tone,
            "keywords": keywords,
            "imagery": imagery,
            "token_count": len(tokens),
        }

    @staticmethod
    def _mood_label(valence: float, energy: float) -> str:
        if valence >= 0.3 and energy >= 0.58:
            return "euphoric"
        if valence >= 0.25:
            return "hopeful"
        if valence <= -0.3 and energy >= 0.58:
            return "furious"
        if valence <= -0.3:
            return "melancholic"
        if energy >= 0.66:
            return "restless"
        if energy <= 0.32:
            return "dreamlike"
        return "introspective"
