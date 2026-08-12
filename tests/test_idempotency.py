"""R8 관문 ①의 심장: 멱등성 키.

"같은 의미의 호출"이 같은 키를 내야 한다. 이게 흔들리면
- 관문 ①이 중복을 통과시키거나 (거짓 음성 → 부작용 2회 발생)
- 관문 ②가 멀쩡한 재생을 DUPLICATE 로 잡는다 (거짓 양성 → 배포가 이유 없이 막힌다)
둘 다 제품을 무의미하게 만든다.
"""

from backstop.idempotency import canonicalize_args, idem_key

SCOPE = "run-1"


def key(args, tool="erp.create_po", scope=SCOPE):
    return idem_key(tool, args, scope)


# --- 같은 의미 → 같은 키 -------------------------------------------------


def test_argument_order_does_not_matter():
    assert key({"vendor_id": "acme", "amount_usd": 10}) == key(
        {"amount_usd": 10, "vendor_id": "acme"}
    )


def test_int_and_integral_float_are_the_same_key():
    """P0 실측 버그. 라이브 Gemini 는 4200 을, 로컬은 4200.0 을 보냈다."""
    assert key({"amount_usd": 4200}) == key({"amount_usd": 4200.0})


def test_surrounding_whitespace_is_ignored():
    assert key({"vendor_id": "acme-corp"}) == key({"vendor_id": "  acme-corp \n"})


def test_unicode_is_normalized():
    # "é" 조합형(U+0065 U+0301) vs 완성형(U+00E9)
    assert key({"note": "café"}) == key({"note": "café"})


def test_explicit_null_equals_omitted_field():
    """모델은 선택 인자를 명시적 null 로 채우기도, 생략하기도 한다."""
    assert key({"vendor_id": "acme", "memo": None}) == key({"vendor_id": "acme"})


def test_nested_dict_order_does_not_matter():
    assert key({"meta": {"a": 1, "b": 2}}) == key({"meta": {"b": 2, "a": 1}})


# --- 다른 의미 → 다른 키 -------------------------------------------------


def test_vendor_id_case_is_deliberately_significant():
    """정규화하지 않는다. 데모가 재현하는 실제 실패 모드다."""
    assert key({"vendor_id": "acme-corp"}) != key({"vendor_id": "ACME Corp"})


def test_tool_name_changes_the_key():
    assert key({"x": 1}, tool="erp.create_po") != key({"x": 1}, tool="mail.send")


def test_run_scope_changes_the_key():
    assert key({"x": 1}, scope="run-1") != key({"x": 1}, scope="run-2")


def test_different_values_change_the_key():
    assert key({"amount_usd": 4200}) != key({"amount_usd": 4201})


def test_list_order_is_significant():
    """리스트 순서는 의미가 있다. dict 키 순서와 다르다."""
    assert key({"items": [1, 2]}) != key({"items": [2, 1]})


def test_bool_is_not_confused_with_int():
    """파이썬에서 bool 은 int 의 서브클래스다. True 와 1 이 같은 키가 되면 안 된다."""
    assert key({"flag": True}) != key({"flag": 1})


# --- 저장 형태 -----------------------------------------------------------


def test_canonical_args_are_json_serializable_for_firestore():
    import json

    canon = canonicalize_args({"amount_usd": 4200.0, "memo": None, "v": " x "})
    json.dumps(canon)  # Firestore 에 map 으로 들어가야 한다
    assert canon == {"amount_usd": 4200, "v": "x"}


def test_key_is_stable_across_calls():
    assert key({"vendor_id": "acme"}) == key({"vendor_id": "acme"})


def test_key_is_hex_sha256():
    k = key({"vendor_id": "acme"})
    assert len(k) == 64 and all(c in "0123456789abcdef" for c in k)
