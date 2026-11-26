import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _is_sys_path_insert(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return False
    func = statement.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "insert"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "path"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "sys"
    )


def _normalized_ast_dump(file_path: Path, strip_sys_path_insert: bool = False) -> str:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    if strip_sys_path_insert:
        tree.body = [stmt for stmt in tree.body if not _is_sys_path_insert(stmt)]

    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            expr_value = body[0].value
            if isinstance(expr_value, ast.Constant) and isinstance(expr_value.value, str):
                node.body = body[1:] or [ast.Pass()]

    return ast.dump(tree, include_attributes=False)


class TestExplainedSync(unittest.TestCase):
    def test_explained_mirror_matches_core_ast(self):
        core_dir = PROJECT_ROOT / "ghostclip"
        explained_dir = PROJECT_ROOT / "explained" / "ghostclip"

        pairs: list[tuple[Path, Path, bool]] = [
            (PROJECT_ROOT / "main.py", PROJECT_ROOT / "explained" / "main.py", True)
        ]
        for source_file in sorted(core_dir.glob("*.py")):
            pairs.append((source_file, explained_dir / source_file.name, False))

        for core_file, twin_file, strip_insert in pairs:
            with self.subTest(file=core_file.relative_to(PROJECT_ROOT).as_posix()):
                self.assertTrue(twin_file.exists(), f"Отсутствует учебный двойник: {twin_file}")
                self.assertEqual(
                    _normalized_ast_dump(core_file),
                    _normalized_ast_dump(twin_file, strip_sys_path_insert=strip_insert),
                )


if __name__ == "__main__":
    unittest.main()
