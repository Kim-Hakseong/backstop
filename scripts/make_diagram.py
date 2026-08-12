"""T5.1: 아키텍처 다이어그램 SVG 생성 (@Design.md §7 규격).

    uv run python scripts/make_diagram.py

규격: 1600×900, 여백 64, 박스 radius 8, 직교 라우팅만(곡선 금지),
필수 기술은 텍스트 배지로(Google 제품 아이콘 사용 금지 — 브랜드 가이드 위반 회피),
관문 ①·②는 붉은 세로 막대, 재생 경로는 점선.

폰트를 base64 로 박아 파일 하나로 완결시킨다. 제출물이라 어디서 열려도 같아야 한다.
"""

from __future__ import annotations

import base64
import pathlib
import sys

BG = "#0A0C10"
SURFACE = "#12151C"
SURFACE2 = "#191D26"
BORDER = "#232937"
BORDER_STRONG = "#323A4D"
FG = "#E8EBF2"
MUTED = "#8A93A6"
DIM = "#5A6274"
BLOCK = "#FF4D4D"
INFO = "#4C8DFF"
PASS = "#3DDC97"

W, H, M = 1600, 900, 64
FONTS = pathlib.Path("api/static/fonts")
OUT = pathlib.Path("docs/architecture.svg")

parts: list[str] = []


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def box(x, y, w, h, title, subtitle=None, fill=SURFACE, stroke=BORDER):
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{x + 20}" y="{y + 32}" class="t">{esc(title)}</text>'
    )
    if subtitle:
        parts.append(
            f'<text x="{x + 20}" y="{y + 54}" class="s">{esc(subtitle)}</text>'
        )


def line(x, y, text, cls="s", anchor="start"):
    parts.append(
        f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{esc(text)}</text>'
    )


def badge(x, y, label):
    w = 11 + len(label) * 7.1
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w:.0f}" height="22" rx="4" '
        f'fill="{INFO}" fill-opacity="0.15"/>'
    )
    parts.append(f'<text x="{x + 8}" y="{y + 15}" class="badge">{esc(label)}</text>')
    return x + w + 8


def arrow(points, colour=BORDER_STRONG, dashed=False, label=None, lx=0, ly=0,
          anchor="start"):
    """직교 폴리라인. 곡선 금지."""
    d = " ".join(f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y) in enumerate(points))
    dash = ' stroke-dasharray="4 4"' if dashed else ""
    parts.append(
        f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="1"{dash} '
        f'marker-end="url(#a{"i" if colour == INFO else ""})"/>'
    )
    if label:
        parts.append(
            f'<text x="{lx}" y="{ly}" class="lbl" fill="{colour}" '
            f'text-anchor="{anchor}">{esc(label)}</text>'
        )


def gate(x, y, h, label, anchor="middle", lx=None):
    """관문: 3px 붉은 세로 막대 + 짧은 라벨."""
    parts.append(f'<rect x="{x}" y="{y}" width="3" height="{h}" fill="{BLOCK}"/>')
    line(lx if lx is not None else x + 1, y + h + 18, label, "gate", anchor)


def font_face(family: str, filename: str, weight: str) -> str:
    data = base64.b64encode((FONTS / filename).read_bytes()).decode()
    return (
        f"@font-face{{font-family:'{family}';font-weight:{weight};"
        f"src:url(data:font/woff2;base64,{data}) format('woff2');}}"
    )


def build() -> str:
    faces = "".join([
        font_face("Inter", "Inter-var.woff2", "100 900"),
        font_face("IBM Plex Mono", "IBMPlexMono-400.woff2", "400"),
        font_face("IBM Plex Mono", "IBMPlexMono-500.woff2", "500"),
    ])

    parts.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')

    # ── 제목 ──────────────────────────────────────────────────────────────
    line(M, 84, "BACKSTOP", "brand")
    line(M, 112, "Replay your agent's last six weeks before you ship the next one.", "lede")
    line(
        M, 136,
        "6 weeks · 1,094 ledger events · 42 side effects · replay+gate 1.7ms · "
        "0 external calls during replay · 3 duplicates blocked",
        "stat",
    )

    # ── 좌: Pub/Sub → subject-agent ──────────────────────────────────────
    box(M, 190, 360, 96, "Pub/Sub", "topic agent.tick — one message = one workflow step")
    badge(M + 20, 252, "Pub/Sub")
    arrow([(M + 180, 286), (M + 180, 310)])

    box(M, 310, 360, 300, "subject-agent", "Cloud Run · Google ADK · 6-week vendor onboarding")
    line(M + 20, 386, "the audited specimen, not the product", "dim")

    box(M + 20, 400, 320, 64, "before_tool_callback", None, SURFACE2)
    line(M + 40, 448, "claim the idempotency key, then run", "dim")
    box(M + 20, 478, 320, 64, "after_tool_callback", None, SURFACE2)
    line(M + 40, 526, "commit effect + OTel span → ledger", "dim")

    bx = badge(M + 20, 556, "Google ADK")
    badge(bx, 556, "Gemini 3.5 Flash")
    badge(M + 20, 584, "Cloud Run")

    # 관문 ① — 부작용이 프로세스를 떠나기 직전
    gate(440, 310, 300, "GATE ①", "middle", 441)

    # ── 중앙: 스텁 / 원장 ────────────────────────────────────────────────
    box(520, 190, 340, 110, "External tool stubs", "erp.create_po · mail.send · payment.schedule")
    line(540, 270, "the only place effects would really leave", "dim")

    box(520, 330, 340, 280, "Firestore ledger", "append-only · document id = idempotency key")
    line(540, 424, "events        1,094", "mono")
    line(540, 452, "effects          42", "mono")
    line(540, 480, "runs              4", "mono")
    line(540, 508, "divergences   gate output", "mono")
    badge(540, 528, "Firestore")
    line(540, 578, "seq orders the replay — never timestamps", "dim")

    # ── 우: backstop-api ─────────────────────────────────────────────────
    box(1000, 190, 536, 430, "backstop-api", "Cloud Run · the product")

    box(1020, 262, 480, 86, "ReplayHarness", None, SURFACE2)
    line(1040, 312, "tool executor → IntentCollector", "mono")
    line(1040, 334, "collects intents, executes nothing", "dim")

    box(1020, 364, 480, 96, "DivergenceGate", None, SURFACE2)
    line(1040, 414, "past effects △ replay intents", "mono")
    line(1040, 436, "pure function · no network, no model import", "dim")

    box(1020, 476, 480, 86, "Narrator", None, SURFACE2)
    line(1040, 526, "Gemini 3.5 Flash · one sentence per card", "mono")
    line(1040, 548, "reads the verdict, cannot change it", "dim")
    badge(1020, 574, "Gemini 3.5 Flash")

    # 관문 ② — 배포 직전
    gate(1516, 364, 96, "GATE ②", "end", 1512)

    # ── 출력 ─────────────────────────────────────────────────────────────
    arrow([(1268, 620), (1268, 676)])
    box(1000, 676, 536, 104, "DEPLOY BLOCKED — exit 1", "Console (one page) · CI: make gate",
        SURFACE, BLOCK)
    line(1020, 756, "DUPLICATE 3   MISSING 0   MUTATED 0", "mono")

    # ── 연결선은 **맨 마지막에** 그린다 ─────────────────────────────────
    # 박스보다 먼저 그리면 라벨이 박스에 덮여 잘린다 ("replay: no egress" 가
    # "replay: no" 로 보였다).
    arrow([(424, 430), (490, 430), (490, 246), (520, 246)],
          label="side effect", lx=512, ly=330, anchor="end")
    arrow([(424, 520), (490, 520), (490, 470), (520, 470)],
          label="event + span", lx=512, ly=560, anchor="end")
    arrow([(860, 470), (1000, 470)], colour=INFO, dashed=True,
          label="replay: no egress", lx=930, ly=452, anchor="middle")

    # ── 각주 ─────────────────────────────────────────────────────────────
    line(M, 838, "GATE ① blocks a duplicate at execution time · GATE ② blocks it at deploy time.", "foot")
    line(M, 858, "LLM is called only inside Narrator — the gate is pure set arithmetic.", "foot")
    line(M, 878, "The six-week ledger is generated by simulation (fixtures/ledger_6w.jsonl), not a real production log.", "foot")

    body = "\n  ".join(parts)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <style>{faces}
    .brand{{font:600 13px Inter;fill:{FG};letter-spacing:.14em}}
    .lede{{font:400 17px Inter;fill:{FG}}}
    .stat{{font:400 12px 'IBM Plex Mono';fill:{MUTED}}}
    .t{{font:600 15px Inter;fill:{FG}}}
    .s{{font:400 12px Inter;fill:{MUTED}}}
    .dim{{font:400 12px Inter;fill:{DIM}}}
    .mono{{font:400 12px 'IBM Plex Mono';fill:{FG}}}
    .badge{{font:500 11px 'IBM Plex Mono';fill:{INFO}}}
    .lbl{{font:400 11px 'IBM Plex Mono'}}
    .gate{{font:500 11px 'IBM Plex Mono';fill:{BLOCK}}}
    .foot{{font:400 11px 'IBM Plex Mono';fill:{DIM}}}
  </style>
  <marker id="a" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
    <path d="M0,0 L4,2.5 L0,5 z" fill="{BORDER_STRONG}"/>
  </marker>
  <marker id="ai" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
    <path d="M0,0 L4,2.5 L0,5 z" fill="{INFO}"/>
  </marker>
</defs>
  {body}
</svg>
'''


def main() -> int:
    if not FONTS.is_dir():
        print("fonts/ not found — run from the repo root", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
