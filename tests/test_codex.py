"""test_codex.py — Codex 模块测试"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from codex import Codex, read_code, search_code, count_loc


def _src(*parts):
    return os.path.join(os.path.dirname(__file__), "..", "src", *parts)


class TestCodex:
    def test_tools_count(self):
        c = Codex()
        assert len(c.tools) == 6

    def test_read_code(self):
        r = read_code(_src("codex.py"), 1, 3)
        assert "Codex" in r
        assert "1|" in r

    def test_read_not_found(self):
        r = read_code("nonexist.py")
        assert "Error" in r

    def test_list_files(self):
        c = Codex()
        r = c.tools["list_files"]["fn"](_src(), "*.py")
        assert "codex.py" in r

    def test_count_loc(self):
        r = count_loc(_src())
        assert "Total" in r

    def test_search_code(self):
        r = search_code("class Codex", _src())
        assert "codex.py" in r

    def test_run_python(self):
        c = Codex()
        r = c.tools["run_python"]["fn"]("print(1+1)")
        assert "2" in r

    def test_edit_code(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        c = Codex(str(tmp_path))
        r = c.tools["edit_code"]["fn"](str(f), "hello", "hi")
        assert "OK" in r
        assert f.read_text() == "hi world"
