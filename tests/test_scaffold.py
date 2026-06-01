"""测试 — 项目脚手架 (scaffold)"""

from pathlib import Path

import pytest

from alpha_id.scaffold_templates import (
    EDITORCONFIG,
    GITIGNORE,
    PRE_COMMIT_CONFIG,
    VSCODE_SETTINGS,
    VSCODE_EXTENSIONS,
    VSCODE_TASKS,
    GITHUB_CI,
    CONTRIBUTING,
    DEV_SETUP_BAT,
    generate_pyproject_toml,
)


class TestTemplates:
    """模板内容的基本校验"""

    def test_gitignore_contains_pycache(self):
        assert "__pycache__" in GITIGNORE

    def test_gitignore_contains_venv(self):
        assert ".venv" in GITIGNORE

    def test_editorconfig_root(self):
        assert "root = true" in EDITORCONFIG

    def test_editorconfig_indent(self):
        assert "indent_size = 4" in EDITORCONFIG

    def test_precommit_has_ruff(self):
        assert "ruff" in PRE_COMMIT_CONFIG

    def test_precommit_has_hooks(self):
        assert "trailing-whitespace" in PRE_COMMIT_CONFIG
        assert "end-of-file-fixer" in PRE_COMMIT_CONFIG

    def test_vscode_settings_has_pytest(self):
        assert "pytestEnabled" in VSCODE_SETTINGS

    def test_vscode_settings_has_ruff(self):
        assert "charliermarsh.ruff" in VSCODE_SETTINGS

    def test_vscode_extensions_includes_ruff(self):
        assert "charliermarsh.ruff" in VSCODE_EXTENSIONS

    def test_vscode_tasks_has_tests(self):
        assert "Run tests" in VSCODE_TASKS
        assert "Lint" in VSCODE_TASKS

    def test_github_ci_has_lint(self):
        assert "Ruff check" in GITHUB_CI

    def test_github_ci_has_test(self):
        assert "Run tests" in GITHUB_CI

    def test_contributing_has_commit_format(self):
        assert "type>" in CONTRIBUTING
        assert "feat" in CONTRIBUTING

    def test_dev_setup_has_pip(self):
        assert "pip install" in DEV_SETUP_BAT

    def test_dev_setup_has_pause(self):
        assert "pause" in DEV_SETUP_BAT


class TestGeneratePyprojectToml:
    """pyproject.toml 生成器测试"""

    def test_basic_structure(self):
        toml = generate_pyproject_toml("my-project", "A test project")
        assert "[project]" in toml
        assert 'name = "my-project"' in toml
        assert 'description = "A test project"' in toml
        assert "my_project" in toml.replace("-", "_")

    def test_src_package_name(self):
        toml = generate_pyproject_toml("my-awesome-tool")
        assert "my_awesome_tool" in toml  # src package

    @pytest.mark.parametrize(
        "section",
        [
            "[tool.ruff]",
            "[tool.pytest.ini_options]",
            "[tool.coverage.run]",
            "[tool.taskipy.tasks]",
        ],
    )
    def test_has_tool_sections(self, section):
        toml = generate_pyproject_toml("test")
        assert section in toml

    def test_has_task_test(self):
        toml = generate_pyproject_toml("test")
        assert 'test = "python -m pytest' in toml

    def test_has_task_lint(self):
        toml = generate_pyproject_toml("test")
        assert 'lint = "ruff check' in toml

    def test_has_task_check_all(self):
        toml = generate_pyproject_toml("test")
        assert "check-all" in toml


class TestScaffoldCLI:
    """CLI 集成测试 — 在临时目录验证"""

    def test_scaffold_init_creates_files(self, tmp_path: Path):
        """aid scaffold init 应该生成所有预期文件"""
        from alpha_id.scaffold_cli import scaffold_init

        target = str(tmp_path / "new-project")

        # 直接调用 scaffold_init（skip_git=True 避免影响 git 检查）
        scaffold_init(
            path=target,
            name="new-project",
            desc="",
            force=False,
            skip_git=True,
        )

        root = Path(target)
        expected = [
            ".editorconfig",
            ".pre-commit-config.yaml",
            "pyproject.toml",
            "CONTRIBUTING.md",
            ".vscode/settings.json",
            ".vscode/extensions.json",
            ".vscode/tasks.json",
            ".github/workflows/ci.yml",
            "scripts/dev_setup.bat",
            "src/new_project/__init__.py",
            "tests/__init__.py",
        ]
        for rel in expected:
            assert (root / rel).exists(), f"缺少文件: {rel}"

        # 验证 pyproject.toml 内容
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        assert "[project]" in pyproject
        assert 'name = "new-project"' in pyproject

    def test_scaffold_no_overwrite(self, tmp_path: Path):
        """已存在的文件不应该被覆盖（默认）"""
        from alpha_id.scaffold_cli import scaffold_init

        target = tmp_path / "existing"
        target.mkdir()
        (target / ".editorconfig").write_text("keep me", encoding="utf-8")

        scaffold_init(path=str(target), name="existing", skip_git=True)

        assert (target / ".editorconfig").read_text(encoding="utf-8") == "keep me"

    def test_scaffold_force_overwrite(self, tmp_path: Path):
        """--force 应该覆盖已存在的文件"""
        from alpha_id.scaffold_cli import scaffold_init

        target = tmp_path / "force-overwrite"
        target.mkdir()
        (target / ".editorconfig").write_text("original", encoding="utf-8")

        scaffold_init(path=str(target), name="force-overwrite", force=True, skip_git=True)

        assert (target / ".editorconfig").read_text(encoding="utf-8") != "original"
