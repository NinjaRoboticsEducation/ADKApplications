from jptranscript_app.tools.html_converter import convert_to_html


def test_convert_to_html_escapes_script_and_builds_closed_toc():
    markdown = """# 東京（とうきょう）*1

**目次**
- 天気の話

## 天気の話
<script>alert(1)</script> 今日（きょう）は天気（てんき）*1がいいです。

---

### 言葉の解説 (Glossary)

1. 天気（てんき）
* **意味:** 空模様のこと。
* **例文:** 今日は天気がいいです。
* **比較:** 「気候」は長期的な傾向です。
"""

    html = convert_to_html(markdown)

    assert "<!DOCTYPE html>" in html
    assert "<title>東京</title>" in html
    assert '<header class="hero">' in html
    assert "<h1>東京</h1>" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert '<div class="layout">' in html
    assert '<aside class="toc">' in html
    assert html.count("<nav") == 1
    assert html.count("</nav>") == 1
    assert 'href="#section-1"' in html
    assert 'class="content-section"' in html
    assert '<ruby>天気<rt>てんき</rt></ruby>' in html


def test_convert_to_html_normalizes_glossary_labels_without_double_colons():
    markdown = """## 本文
難しい表現*1です。

---

### 言葉の解説 (Glossary)

1. 難しい表現
* **意味 (Meaning):** 説明です。
* **例文 (Examples):** 例です。
* **比較 (Comparison):** 比較です。
"""

    html = convert_to_html(markdown)

    assert "<strong>意味 (Meaning):</strong> 説明です。" in html
    assert "::</strong>" not in html
    assert "glossary-section" in html
    assert 'class="glossary-entry"' in html
    assert 'class="glossary-number"' in html


def test_convert_to_html_handles_bold_furigana_timestamps_and_unique_backrefs():
    markdown = """## 自己紹介
**美和（みわ）**：こんにちは。
2:38
天気（てんき）*1は大事です。天気（てんき）*1も確認します。

---

### 言葉の解説 (Glossary)

1. 天気（てんき）
* **意味:** 空模様のこと。
* **例文:** 今日は天気がいいです。
* **比較:** 「気候」は長期的な傾向です。
"""

    html = convert_to_html(markdown)

    assert '<p class="dialogue">' in html
    assert '<strong class="speaker"><ruby>美和<rt>みわ</rt></ruby></strong>' in html
    assert '<span class="dialogue-text">こんにちは。</span>' in html
    assert '<time datetime="PT2M38S">2:38</time>' in html
    assert 'id="ref-1-1"' in html
    assert 'id="ref-1-2"' in html
    assert 'href="#ref-1-1"' in html
