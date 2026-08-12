"""P0 스캐폴드 확인. 패키지 3개가 import 되고 Makefile 타깃이 전부 존재하는지."""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
REQUIRED_TARGETS = {"setup", "test", "replay", "gate", "bench", "deploy", "demo"}


def test_packages_import():
    import api  # noqa: F401
    import backstop  # noqa: F401
    import subject_agent  # noqa: F401


def test_makefile_has_all_targets():
    text = (REPO / "Makefile").read_text()
    found = set(re.findall(r"^([a-z]+):", text, re.MULTILINE))
    assert REQUIRED_TARGETS <= found, f"missing: {REQUIRED_TARGETS - found}"
