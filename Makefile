.PHONY: setup test replay gate bench deploy demo

setup:
	uv sync

test:
	uv run pytest

# 시드 원장 재생. API 키 불필요.
replay:
	BACKSTOP_OFFLINE=1 uv run python -m backstop.cli replay

# 재생 + 분기 게이트. DUPLICATE 1건 이상이면 종료 코드 1. CI에서 이걸 씀.
gate:
	BACKSTOP_OFFLINE=1 uv run python -m backstop.cli gate

# 이벤트 수 / 재생 소요 / LLM 호출 수 / 차단 건수
bench:
	BACKSTOP_OFFLINE=1 uv run python -m backstop.cli bench

deploy:
	./scripts/deploy.sh

demo:
	uv run python -m backstop.cli demo
