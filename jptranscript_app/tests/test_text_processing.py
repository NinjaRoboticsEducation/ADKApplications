import pytest

from jptranscript_app.tools import text_processing
from jptranscript_app.tools.text_processing import InputResolutionError
from jptranscript_app.tools.text_processing import collapse_meaningless_japanese_spacing
from jptranscript_app.tools.text_processing import chunk_text_with_metadata
from jptranscript_app.tools.text_processing import detect_input_text
from jptranscript_app.tools.text_processing import extract_timestamps
from jptranscript_app.tools.text_processing import protect_timestamps
from jptranscript_app.tools.text_processing import restore_timestamps
from jptranscript_app.tools.text_processing import validate_glossary
from jptranscript_app.tools.text_processing import validate_optimization
from jptranscript_app.tools.text_processing import validate_paragraph


def test_chunk_text_with_metadata_records_overlap_and_boundaries():
    text = ("A" * 450) + "\n\n" + ("B" * 450) + "\n\n" + ("C" * 450)

    chunks = chunk_text_with_metadata(text, max_chars=600, overlap_chars=40)

    assert len(chunks) == 3
    assert chunks[0].text.startswith("A" * 40)
    assert chunks[1].text.startswith("B" * 40)
    assert len(chunks[1].overlap_prefix) == 40
    assert chunks[1].overlap_prefix.startswith("A")
    assert len(chunks[2].overlap_prefix) == 40
    assert chunks[2].overlap_prefix.startswith("B")


def test_detect_input_text_reads_relative_file_and_blocks_escape(monkeypatch, tmp_path):
    monkeypatch.setattr(text_processing, "APP_DIR", tmp_path)
    transcript_path = tmp_path / "sample.txt"
    transcript_path.write_text("日本語のテキストです。", encoding="utf-8")

    text, source_type, label = detect_input_text("sample.txt")

    assert text == "日本語のテキストです。"
    assert source_type == "file"
    assert label == "sample.txt"

    with pytest.raises(InputResolutionError):
        detect_input_text("../escape.txt")


def test_validate_optimization_rejects_chunk_markers():
    source = "田中：今日はいい天気ですね。"
    bad_output = "[Processing chunk 1 of 2]\n田中：今日はいい天気ですね。"

    report = validate_optimization(source, bad_output)

    assert report["chunk_marker_leak"] is True
    assert report["pass"] is False


def test_collapse_meaningless_japanese_spacing_repairs_character_gaps():
    spaced = "皆 さ ん は 絵 を 描 く の が 好 き で す か？\njlpt N3 く ら い の 日 本 語 で す。"

    repaired = collapse_meaningless_japanese_spacing(spaced)

    assert repaired == "皆さんは絵を描くのが好きですか？\njlpt N3くらいの日本語です。"


def test_validate_optimization_requires_spacing_improvement():
    source = "皆 さ ん は 絵 を 描 く の が 好 き で す か？\n今 日 は 絵 に 関 す る 日 本 語 で す。"
    repaired = "皆さんは絵を描くのが好きですか？\n今日は絵に関する日本語です。"
    unchanged = source

    good_report = validate_optimization(source, repaired)
    bad_report = validate_optimization(source, unchanged)

    assert good_report["spacing_improved"] is True
    assert bad_report["spacing_improved"] is False


def test_timestamp_helpers_round_trip_and_extract():
    text = "0:08\n本文です。\n[00:15:30]\n次の本文です。"

    protected = protect_timestamps(text)
    restored = restore_timestamps(protected)

    assert "[[TIMESTAMP:0:08]]" in protected
    assert "[[TIMESTAMP:00:15:30]]" in protected
    assert restored == "0:08\n本文です。\n00:15:30\n次の本文です。"
    assert extract_timestamps(restored) == ["0:08", "00:15:30"]


def test_validate_paragraph_requires_toc_and_headings():
    source = "今日はいい天気です。明日は雨が降るかもしれません。"
    good_output = (
        "**目次**\n"
        "- 天気の話\n\n"
        "## 天気の話\n"
        "今日はいい天気です。明日は雨が降るかもしれません。"
    )
    bad_output = "今日はいい天気です。明日は雨が降るかもしれません。"

    assert validate_paragraph(source, good_output)["pass"] is True
    assert validate_paragraph(source, bad_output)["pass"] is False


def test_validate_paragraph_requires_timestamps_to_survive():
    source = "0:08\n今日はいい天気です。"
    good_output = "**目次**\n- 天気の話\n\n## 天気の話\n0:08\n今日はいい天気です。"
    bad_output = "**目次**\n- 天気の話\n\n## 天気の話\n今日はいい天気です。"

    assert validate_paragraph(source, good_output)["pass"] is True
    assert validate_paragraph(source, bad_output)["timestamps_preserved"] is False


def test_validate_glossary_requires_all_fields():
    good_text = (
        "難しい表現*1があります。\n\n"
        "---\n\n"
        "### 言葉の解説 (Glossary)\n\n"
        "1. 難しい表現\n"
        "* **意味:** 表現の意味です。\n"
        "* **例文:** これは例文です。\n"
        "* **比較:** 類似表現との違いです。\n"
    )
    bad_text = (
        "難しい表現*1があります。\n\n"
        "---\n\n"
        "### 言葉の解説 (Glossary)\n\n"
        "1. 難しい表現\n"
        "* **意味:** 表現の意味です。\n"
    )

    assert validate_glossary(good_text)["pass"] is True
    assert validate_glossary(bad_text)["pass"] is False
