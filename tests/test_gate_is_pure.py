"""R6 불변식: 판정에는 LLM 이 없다.

제출물 첫 단락에 "Backstop 에서 LLM 은 아무것도 차단하지 않는다"고 쓴다. 그 문장이
사실이려면 게이트 모듈이 모델·네트워크에 **닿을 수 없어야** 한다. 주석이 아니라
import 그래프로 강제한다.

두 겹으로 검사한다.
1. 소스의 import 문 (AST) — 직접 import
2. 전이 import 그래프 — 다른 모듈을 타고 들어오는 경우
"""

import ast
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GATE = REPO / "backstop" / "divergence.py"

FORBIDDEN_ROOTS = {
    "google",
    "vertexai",
    "httpx",
    "requests",
    "urllib",
    "socket",
    "http",
    "aiohttp",
    "openai",
    "anthropic",
}

# 표준 라이브러리만 허용한다. 게이트는 순수 계산이므로 이걸로 충분해야 한다.
ALLOWED = {"__future__", "dataclasses", "typing", "collections", "itertools", "math"}


def _imported_roots(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_gate_imports_nothing_forbidden():
    assert not (_imported_roots(GATE) & FORBIDDEN_ROOTS)


def test_gate_imports_only_stdlib_essentials():
    """허용 목록 방식. 새 의존성이 슬며시 들어오면 여기서 걸린다."""
    unexpected = _imported_roots(GATE) - ALLOWED
    assert not unexpected, f"게이트에 예상 밖 import: {unexpected}"


def test_gate_does_not_import_the_replay_engine():
    """게이트가 재생 구현에 묶이면 순수성을 잃는다. 입력은 덕 타이핑된 데이터다."""
    assert "backstop" not in _imported_roots(GATE)


def test_gate_module_pulls_in_no_network_modules_transitively():
    """전이 검사. divergence 만 새로 import 했을 때 무엇이 딸려오는지 본다."""
    for name in list(sys.modules):
        if name.startswith("backstop.divergence"):
            del sys.modules[name]

    before = set(sys.modules)
    import backstop.divergence  # noqa: F401

    pulled = set(sys.modules) - before
    offenders = {
        m for m in pulled if m.split(".")[0] in (FORBIDDEN_ROOTS - {"urllib", "http"})
    }
    assert not offenders, f"게이트가 끌어온 금지 모듈: {offenders}"


def test_gate_has_no_llm_in_the_decision_path():
    """판정 함수들이 순수한지: 같은 입력에 항상 같은 출력."""
    from backstop.divergence import compute, exit_code

    class E:
        def __init__(self, key, step=0):
            self.run_id = "r"
            self.step_index = step
            self.tool_name = "erp.create_po"
            self.args_canonical = {"vendor_id": "acme-corp", "line_item": "x"}
            self.idem_key = key
            self.target = "erp.create_po#PO-1"

    class I(E):
        def __init__(self, key, step=0):
            super().__init__(key, step)
            self.args_canonical = {"vendor_id": "ACME Corp", "line_item": "x"}

    past, intents = [E("a")], [I("b")]
    first = compute(past, intents)
    for _ in range(5):
        assert compute(past, intents) == first
    assert exit_code(first) == 1


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_ROOTS))
def test_forbidden_root_is_actually_absent(forbidden):
    assert forbidden not in _imported_roots(GATE)
