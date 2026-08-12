"""관문 ① 의 키 계산 (R8).

`idem_key(tool_name, args, run_scope)` 가 프로젝트의 심장이다. "같은 의미의 호출"이
같은 키를 내지 못하면 관문 ①은 중복을 통과시키고 관문 ②는 멀쩡한 재생을 DUPLICATE 로
잡는다. 규칙은 README 의 정규화 표와 1:1로 대응한다.

이 모듈은 순수하다. 네트워크도 LLM 도 시계도 쓰지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

# 정규화 규칙 버전. 규칙을 바꾸면 과거 키와 비교가 불가능해지므로 올린다.
# (프롬프트 변경이 키를 흔드는 문제는 미해결이다 — README·write-up 에 명시)
CANON_VERSION = "1"


def _canonical_value(value: Any) -> Any:
    # bool 이 int 서브클래스라는 점을 먼저 처리한다. True 와 1 은 다른 값이다.
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # 정수와 정수형 float 를 하나로 모은다. LLM 은 4200 과 4200.0 을 섞어 보낸다.
        return int(value) if value.is_integer() else value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value).strip()
    if isinstance(value, dict):
        return canonicalize_args(value)
    if isinstance(value, (list, tuple)):
        # 리스트 순서는 의미가 있다. 정렬하지 않는다.
        return [_canonical_value(v) for v in value]
    return value


def canonicalize_args(args: dict[str, Any]) -> dict[str, Any]:
    """인자를 정규 형태로 바꾼다. 이 결과가 `events.args_canonical` 로 저장된다.

    - None 값 필드는 제거한다 (명시적 null 과 생략을 같게 본다)
    - 문자열은 NFC 정규화 + 앞뒤 공백 제거
    - 정수형 float 는 int 로 모은다
    - dict 는 재귀 적용. 키 순서는 직렬화 시점에 정렬한다
    """
    return {
        k: _canonical_value(v)
        for k, v in args.items()
        if v is not None
    }


def canonical_repr(tool_name: str, args: dict[str, Any], run_scope: str) -> str:
    """해시 입력이 되는 문자열. 디버깅 시 사람이 눈으로 비교할 수 있게 노출한다."""
    payload = {
        "v": CANON_VERSION,
        "tool": tool_name,
        "scope": run_scope,
        "args": canonicalize_args(args),
    }
    # sort_keys 가 dict 키 순서를 흡수한다. bool 은 JSON 에서 true/false 로 나가
    # 정수 1 과 구분된다.
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def idem_key(tool_name: str, args: dict[str, Any], run_scope: str) -> str:
    """`(도구명, 정규화된 인자, 실행 범위)` 의 sha256 hex."""
    return hashlib.sha256(
        canonical_repr(tool_name, args, run_scope).encode("utf-8")
    ).hexdigest()
