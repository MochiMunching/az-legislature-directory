"""Wrap site/body.html in a full HTML document and write index.html at the repo root
(the file GitHub Pages serves). Run after editing site/body.html."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
body = (root / "site" / "body.html").read_text(encoding="utf-8")
head_end = body.index("</style>") + len("</style>")
html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{body[:head_end]}
</head>
<body>
{body[head_end:].strip()}
</body>
</html>
"""
(root / "index.html").write_text(html, encoding="utf-8")
print("wrote index.html")
