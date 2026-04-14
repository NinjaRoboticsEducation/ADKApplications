from jptranscript_app.tools.furigana_tools import auto_add_furigana
from jptranscript_app.tools.furigana_tools import extract_furigana_spans
from jptranscript_app.tools.furigana_tools import refine_furigana
from jptranscript_app.tools.furigana_tools import validate_furigana


def test_auto_add_furigana_preserves_existing_annotation():
    text = "東京（とうきょう）に行きました。"

    annotated = auto_add_furigana(text)

    assert annotated.count("東京（とうきょう）") == 1


def test_extract_furigana_spans_targets_only_the_annotated_token():
    text = "これは東京（とうきょう）です。"

    spans = extract_furigana_spans(text)

    assert len(spans) == 1
    assert spans[0].written == "東京"
    assert spans[0].reading == "とうきょう"


def test_refine_furigana_removes_common_word_and_preserves_surrounding_text():
    text = "これは東京（とうきょう）です。"

    refined = refine_furigana(text)

    assert refined == "これは東京です。"


def test_refine_furigana_limits_repetition_after_three_occurrences():
    text = "桜（さくら）と桜（さくら）と桜（さくら）と桜（さくら）"

    refined = refine_furigana(text)

    assert refined.count("桜（さくら）") == 3
    assert refined.endswith("桜")


def test_validate_furigana_rejects_half_width_parentheses():
    report = validate_furigana("今日(きょう)は天気(てんき)がいいです。")

    assert report["format_correct"] is False
    assert report["pass"] is False
