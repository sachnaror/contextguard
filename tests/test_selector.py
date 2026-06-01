from contextguardrail.selector import prompt_terms, prune_weak_matches, score_row


def test_style_prompt_prefers_css_over_weak_html_matches():
    terms = prompt_terms("Which files control page styling?")
    css = {
        "path": "css/styles.css",
        "summary": "File: css/styles.css",
        "keywords": "button\nlayout\nstyle",
        "classes": "",
        "functions": "",
    }
    html = {
        "path": "about.html",
        "summary": "File: about.html",
        "keywords": "about\ncontact\nstyles",
        "classes": "",
        "functions": "",
    }

    candidates = sorted(
        [(score_row(css, terms), css), (score_row(html, terms), html)],
        key=lambda item: -item[0],
    )

    assert [item["path"] for _, item in prune_weak_matches(candidates)] == ["css/styles.css"]


def test_contact_form_prompt_keeps_contact_page_and_js_handler():
    terms = prompt_terms("Where is the contact form handled?")
    contact = {
        "path": "contact.html",
        "summary": "File: contact.html",
        "keywords": "contact\nform\nenquiry",
        "classes": "",
        "functions": "",
    }
    handler = {
        "path": "js/main.js",
        "summary": "File: js/main.js",
        "keywords": "contactform\nformnote\nsubmit",
        "classes": "",
        "functions": "",
    }
    weak = {
        "path": "about.html",
        "summary": "File: about.html",
        "keywords": "contact\nabout",
        "classes": "",
        "functions": "",
    }

    candidates = sorted(
        [(score_row(contact, terms), contact), (score_row(handler, terms), handler), (score_row(weak, terms), weak)],
        key=lambda item: -item[0],
    )

    assert [item["path"] for _, item in prune_weak_matches(candidates)] == [
        "contact.html",
        "js/main.js",
    ]
