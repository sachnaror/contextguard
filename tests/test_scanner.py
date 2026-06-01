from contextguardrail.scanner import should_scan


def test_should_scan_supported_extensions(tmp_path):
    for name in [
        "app.py",
        "README.md",
        "styles.css",
        "main.js",
        "index.html",
        "notes.txt",
        ".env",
        ".env.example",
        "settings.example",
        "package.json",
    ]:
        path = tmp_path / name
        path.write_text("demo", encoding="utf-8")
        assert should_scan(path, path.relative_to(tmp_path))


def test_should_scan_dockerfile_without_extension(tmp_path):
    path = tmp_path / "Dockerfile"
    path.write_text("FROM python:3.12", encoding="utf-8")
    assert should_scan(path, path.relative_to(tmp_path))


def test_should_skip_unsupported_extension(tmp_path):
    path = tmp_path / "image.png"
    path.write_text("demo", encoding="utf-8")
    assert not should_scan(path, path.relative_to(tmp_path))
