from tools.registry import run_tool

def test_project_status():
    result = run_tool("project_status", {})
    assert "Aster Voss" in result

def test_file_escape():
    result = run_tool("read_project_file", {"path": "../../etc/passwd"})
    assert result.startswith("Refused:")


def test_tool_permission_default_is_read_only():
    from tools.registry import run_tool
    assert "Refused" in run_tool("read_project_file", {"path": "agent.py"}, allowed_permissions={"write"})
