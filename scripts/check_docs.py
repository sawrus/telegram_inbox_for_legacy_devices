"""Check local Markdown links in the maintained documentation."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def main():
    errors = []
    for source in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        for target in LINK.findall(source.read_text(encoding="utf-8")):
            parsed = urlsplit(target.strip().split()[0].strip("<>"))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            path = Path(unquote(parsed.path))
            destination = ROOT / str(path).lstrip("/") if path.is_absolute() else source.parent / path
            if not destination.exists():
                errors.append(f"{source.relative_to(ROOT)}: missing {target}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Local documentation links OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
