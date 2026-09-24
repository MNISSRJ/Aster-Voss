from tools.registry import run_tool

def test_project_status():
    result = run_tool("project_status", {})
    assert "Aster Voss" in result

def test_file_escape():
    result = run_tool("read_project_file", {"path": "../../etc/passwd"})
    assert result.startswith("Refused:")
