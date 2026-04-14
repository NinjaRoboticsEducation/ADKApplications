"""
Furigana utilities for the local transcript workflow.

The key requirement here is correctness over cleverness: we rely on fugashi for
annotation, and we parse existing furigana spans carefully so refinement never
modifies unrelated sentence text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import fugashi


_tagger = None


def _get_tagger():
    global _tagger
    if _tagger is None:
        _tagger = fugashi.Tagger()
    return _tagger


@dataclass(frozen=True)
class FuriganaSpan:
    start: int
    open_paren: int
    end: int
    written: str
    reading: str


def _contains_kanji(text: str) -> bool:
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            return True
    return False


def _is_hiragana(text: str) -> bool:
    return bool(text) and all("\u3040" <= ch <= "\u309f" or ch in "ー・" for ch in text)


def _is_token_char(ch: str) -> bool:
    return (
        "\u3040" <= ch <= "\u309f"
        or "\u30a0" <= ch <= "\u30ff"
        or "\u3400" <= ch <= "\u4dbf"
        or "\u4e00" <= ch <= "\u9fff"
        or ch in "々ゝゞー・ヵヶ"
    )


def _kata_to_hira(text: str) -> str:
    converted: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            converted.append(chr(code - 0x60))
        else:
            converted.append(ch)
    return "".join(converted)


def _has_existing_furigana(text: str, pos: int, surface: str) -> bool:
    end = pos + len(surface)
    if end < len(text) and text[end] == "（":
        close = text.find("）", end)
        if close != -1:
            return _is_hiragana(text[end + 1 : close])
    return False


def auto_add_furigana(text: str) -> str:
    """Add furigana using fugashi while preserving existing structure."""
    tagger = _get_tagger()
    lines = text.split("\n")
    return "\n".join(_add_furigana_to_line(line, tagger) for line in lines)


def _add_furigana_to_line(line: str, tagger) -> str:
    if not line.strip():
        return line

    words = tagger(line)
    result: list[str] = []
    pos = 0

    for word in words:
        surface = word.surface
        idx = line.find(surface, pos)
        if idx == -1:
            result.append(surface)
            continue

        if idx > pos:
            result.append(line[pos:idx])

        if _has_existing_furigana(line, idx, surface):
            close = line.find("）", idx + len(surface))
            result.append(line[idx : close + 1])
            pos = close + 1
            continue

        if _contains_kanji(surface) and getattr(word.feature, "kana", None):
            reading = _kata_to_hira(word.feature.kana)
            if reading != surface:
                result.append(f"{surface}（{reading}）")
            else:
                result.append(surface)
        else:
            result.append(surface)

        pos = idx + len(surface)

    if pos < len(line):
        result.append(line[pos:])
    return "".join(result)


def extract_furigana_spans(text: str) -> list[FuriganaSpan]:
    """
    Parse existing ``漢字（かんじ）`` spans without accidentally swallowing
    surrounding sentence text.
    """
    spans: list[FuriganaSpan] = []
    tagger = _get_tagger()
    index = 0

    while index < len(text):
        open_idx = text.find("（", index)
        if open_idx == -1:
            break
        close_idx = text.find("）", open_idx + 1)
        if close_idx == -1:
            break

        reading = text[open_idx + 1 : close_idx]
        if not _is_hiragana(reading):
            index = open_idx + 1
            continue

        scan_start = open_idx - 1
        while scan_start >= 0 and _is_token_char(text[scan_start]):
            scan_start -= 1
        scan_start += 1

        candidate = text[scan_start:open_idx]
        if not candidate:
            index = close_idx + 1
            continue

        tokens = list(tagger(candidate))
        if tokens:
            written = tokens[-1].surface
            start = open_idx - len(written)
        else:
            written = candidate
            start = scan_start

        if _contains_kanji(written):
            spans.append(
                FuriganaSpan(
                    start=start,
                    open_paren=open_idx,
                    end=close_idx + 1,
                    written=written,
                    reading=reading,
                )
            )

        index = close_idx + 1

    return spans


def validate_furigana(text: str) -> dict[str, object]:
    """Validate furigana coverage and formatting."""
    tagger = _get_tagger()
    spans = extract_furigana_spans(text)
    base_text = re.sub(r"（[ぁ-ん]+）", "", text)

    words = tagger(base_text)
    total_kanji_words = len([word for word in words if _contains_kanji(word.surface)])
    coverage = len(spans) / total_kanji_words if total_kanji_words else 1.0
    half_width = len(re.findall(r"\([ぁ-ん]+\)", text))

    return {
        "total_kanji_words": total_kanji_words,
        "furigana_annotations": len(spans),
        "coverage": round(coverage, 3),
        "coverage_pass": coverage >= 0.90,
        "format_correct": half_width == 0,
        "pass": coverage >= 0.90 and half_width == 0,
    }


COMMON_WORDS = [
    ("日本", ["にほん"]),
    ("私", ["わたし"]),
    ("行", ["い"]),
    ("中", ["なか"]),
    ("方", ["かた", "ほう"]),
    ("思", ["おも"]),
    ("感", ["かん"]),
    ("何", ["なに", "なん"]),
    ("皆", ["みな"]),
    ("知", ["し"]),
    ("間", ["あいだ"]),
    ("国", ["くに"]),
    ("約", ["やく"]),
    ("多", ["おお"]),
    ("人", ["ひと", "にん"]),
    ("本当", ["ほんとう"]),
    ("行", ["おこな"]),
    ("大", ["おお"]),
    ("近", ["ちか"]),
    ("見", ["み"]),
    ("今回", ["こんかい"]),
    ("金", ["かね"]),
    ("買", ["か"]),
    ("来", ["く", "き"]),
    ("人気", ["にんき"]),
    ("食", ["た"]),
    ("良", ["よ"]),
    ("入", ["い"]),
    ("聞", ["き"]),
    ("道", ["みち"]),
    ("立", ["た"]),
    ("日本語", ["にほんご"]),
    ("毎週", ["まいしゅう"]),
    ("会", ["あ"]),
    ("前", ["まえ"]),
    ("結構", ["けっこう"]),
    ("一番", ["いちばん"]),
    ("旅行", ["りょこう"]),
    ("話", ["はなし"]),
    ("後", ["あと"]),
    ("作", ["つく"]),
    ("自分", ["じぶん"]),
    ("彼", ["かれ"]),
    ("例", ["れい", "たと"]),
    ("興味", ["きょうみ"]),
    ("最", ["もっと"]),
    ("言", ["い"]),
    ("今", ["いま"]),
    ("問題", ["もんだい"]),
    ("実", ["じつ"]),
    ("時", ["とき"]),
    ("出", ["で"]),
    ("決", ["き"]),
    ("一", ["ひと"]),
    ("場所", ["ばしょ"]),
    ("今日", ["きょう"]),
    ("最近", ["さいきん"]),
    ("年", ["ねん"]),
    ("月", ["がつ"]),
    ("日", ["ひ"]),
    ("分", ["ふん"]),
    ("秒", ["びょう"]),
    ("元気", ["げんき"]),
    ("考", ["かんが"]),
    ("元", ["もと"]),
    ("手", ["て"]),
    ("世界", ["せかい"]),
    ("先", ["さき"]),
    ("活動", ["かつどう"]),
    ("対", ["たい"]),
    ("上", ["うえ", "あ"]),
    ("生活", ["せいかつ"]),
    ("時代", ["じだい"]),
    ("東京", ["とうきょう"]),
    ("頃", ["ころ"]),
    ("子供", ["こども"]),
    ("学校", ["がっこう"]),
    ("使", ["つか"]),
]

_COMMON_LOOKUP: dict[str, set[str]] = {}
for written, readings in COMMON_WORDS:
    _COMMON_LOOKUP.setdefault(written, set()).update(readings)


def refine_furigana(text: str) -> str:
    """
    Remove furigana for common words and repeated items without touching
    unrelated text.
    """
    spans = extract_furigana_spans(text)
    if not spans:
        return text

    seen_count: dict[tuple[str, str], int] = {}
    result: list[str] = []
    cursor = 0

    for span in spans:
        result.append(text[cursor : span.start])
        key = (span.written, span.reading)

        if _is_common_word_match(span.written, span.reading):
            result.append(span.written)
        else:
            count = seen_count.get(key, 0)
            seen_count[key] = count + 1
            if count < 3:
                result.append(text[span.start : span.end])
            else:
                result.append(span.written)

        cursor = span.end

    result.append(text[cursor:])
    return "".join(result)


def _is_common_word_match(written: str, reading: str) -> bool:
    if written in _COMMON_LOOKUP:
        if any(
            reading == common_reading or reading.startswith(common_reading)
            for common_reading in _COMMON_LOOKUP[written]
        ):
            return True

    for stem, readings in _COMMON_LOOKUP.items():
        if len(stem) == 1 and written.startswith(stem) and len(written) > 1:
            if any(reading.startswith(stem_reading) for stem_reading in readings):
                return True

    return False
