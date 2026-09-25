from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def test_inline_ui_script_passes_node_syntax_check():
    match = re.search(r"<script>(.*?)</script>", SOURCE, re.DOTALL)
    assert match, "Expected the UI to contain one inline <script> block"

    node = shutil.which("node")
    assert node, (
        "JavaScript syntax regression test requires Node.js on the test runner. "
        "Install Node or enable actions/setup-node in CI."
    )

    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
        handle.write(match.group(1))
        script_path = handle.name

    try:
        result = subprocess.run(
            [node, "--check", script_path],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            "Inline UI JavaScript failed node --check:\n"
            + result.stdout
            + result.stderr
        )
    finally:
        Path(script_path).unlink(missing_ok=True)
