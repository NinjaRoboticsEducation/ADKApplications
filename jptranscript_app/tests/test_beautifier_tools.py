from jptranscript_app.tools.beautifier_tools import apply_design_template


def test_apply_design_template_replaces_style_without_external_font_url():
    html = """<!DOCTYPE html>
<html lang="ja">
<head>
  <style>
    body { margin: 0; }
  </style>
</head>
<body>
  <p>Test</p>
</body>
</html>"""

    beautified = apply_design_template(html)

    assert "--bg:" in beautified
    assert "fonts.googleapis.com" not in beautified
    assert beautified.count("<style>") == 1


def test_apply_design_template_injects_style_when_missing():
    html = """<!DOCTYPE html>
<html lang="ja">
<head>
</head>
<body>
  <p>Test</p>
</body>
</html>"""

    beautified = apply_design_template(html)

    assert "<style>" in beautified
    assert "</head>" in beautified
