import griffe
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
WIDGET = FIXTURES / "widget_fixture.py"


def main():
    with TemporaryDirectory() as tmpdir:
        package = Path(tmpdir) / "widpkg"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        widget = package / "widget.py"
        widget.write_text(WIDGET.read_text(encoding="utf-8"), encoding="utf-8")
        sys.path.insert(0, tmpdir)

        pkg = griffe.load("widpkg")
        __import__("pdb").set_trace()


if __name__ == "__main__":
    main()
