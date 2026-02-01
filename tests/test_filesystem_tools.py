import os
import sys
import pytest

# Ensure repo root is on sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.tools import FileReadTool, FileWriteTool


@pytest.mark.asyncio
async def test_file_tools_base_path_enforced(tmp_path):
    base_dir = tmp_path / "safe"
    base_dir.mkdir()
    safe_file = base_dir / "ok.txt"
    safe_file.write_text("hi", encoding="utf-8")

    outside_dir = tmp_path / "safe_evil"
    outside_dir.mkdir()
    outside_file = outside_dir / "evil.txt"
    outside_file.write_text("no", encoding="utf-8")

    read_tool = FileReadTool(base_path=str(base_dir))
    res_ok = await read_tool.run(path=str(safe_file))
    assert res_ok == "hi"

    res_bad = await read_tool.run(path=str(outside_file))
    assert "Access denied" in res_bad

    write_tool = FileWriteTool(base_path=str(base_dir))
    res_write_ok = await write_tool.run(path=str(base_dir / "write.txt"), content="ok")
    assert res_write_ok.startswith("Wrote")

    res_write_bad = await write_tool.run(path=str(outside_dir / "write.txt"), content="x")
    assert "Access denied" in res_write_bad
