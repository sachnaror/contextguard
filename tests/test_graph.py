from pathlib import Path

from contextguardrail.graph import parse_file


def test_parse_javascript_functions_and_imports():
    parsed = parse_file(
        Path("main.js"),
        "main.js",
        "import helper from './helper.js';\nfunction submitForm() {}\nconst animate = () => {};",
    )

    assert "./helper.js" in parsed["imports"]
    assert "submitForm" in parsed["functions"]
    assert "animate" in parsed["functions"]


def test_parse_html_links_classes_and_tags():
    parsed = parse_file(
        Path("contact.html"),
        "contact.html",
        '<link href="css/styles.css"><form id="contactForm" class="hero contact"></form>',
    )

    assert "css/styles.css" in parsed["imports"]
    assert "contactForm" in parsed["classes"]
    assert "contact" in parsed["classes"]
    assert "form" in parsed["functions"]


def test_parse_css_selectors():
    parsed = parse_file(Path("styles.css"), "styles.css", ".hero { color: red; }\n#contactForm { }")

    assert ".hero" in parsed["classes"]
    assert "#contactForm" in parsed["classes"]
