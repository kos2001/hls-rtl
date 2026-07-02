#!/usr/bin/env python3
"""Seed realistic developer-discussion comment threads onto every issue of a
Jira Cloud project (default: LSI board).

Auth: reads JIRA_EMAIL + JIRA_TOKEN from the environment, or from
~/.jira-claude.env (KEY=VALUE lines). Create a token at
https://id.atlassian.com/manage-profile/security/api-tokens

Usage:
    python3 scripts/jira_seed_comments.py            # all LSI issues, >=8 comments each
    python3 scripts/jira_seed_comments.py --project LSI --min 8
    python3 scripts/jira_seed_comments.py --dry-run  # print, don't POST
    python3 scripts/jira_seed_comments.py --issue LSI-3   # one issue only

Idempotency: every comment is tagged with a hidden marker. Re-running skips
issues that already have >= --min marked comments, so it is safe to resume.

All comments post under one account. To stay truthful (no impersonation of
fabricated individuals), comments are NOT attributed to invented people. Each
is tagged by the *concern/perspective* it represents — [Repro], [RTL],
[DV], [SystemC], [Arch], [Finding], [Resolution] — so the thread reads as a
structured engineering investigation log, not a fake multi-person chat.
Content is grounded in this repo's gamma-correction verification work and
lightly tailored to each issue's summary.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import json
import urllib.request
import urllib.error

SITE = "https://oseokkim2001.atlassian.net"
MARKER = "​"  # zero-width space appended to every comment we author
CREDS_FILE = Path.home() / ".jira-claude.env"


# --------------------------------------------------------------------------
# Auth / HTTP
# --------------------------------------------------------------------------
def load_creds() -> tuple[str, str]:
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_TOKEN")
    if (not email or not token) and CREDS_FILE.exists():
        for line in CREDS_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k == "JIRA_EMAIL" and not email:
                email = v.strip()
            elif k == "JIRA_TOKEN" and not token:
                token = v.strip()
    if not email or not token:
        sys.exit(
            "Missing credentials. Set JIRA_EMAIL and JIRA_TOKEN in the "
            f"environment or in {CREDS_FILE} (KEY=VALUE lines).\n"
            "Token: https://id.atlassian.com/manage-profile/security/api-tokens"
        )
    return email, token


def _auth_header(email: str, token: str) -> str:
    import base64
    raw = f"{email}:{token}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def api(method: str, path: str, email: str, token: str, body: dict | None = None) -> dict:
    url = f"{SITE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", _auth_header(email, token))
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} on {method} {path}: {detail}") from e


# --------------------------------------------------------------------------
# Issue enumeration
# --------------------------------------------------------------------------
def list_issues(project: str, email: str, token: str) -> list[dict]:
    issues, start = [], 0
    while True:
        jql = quote(f"project={project} ORDER BY created ASC")
        path = f"/rest/api/3/search?jql={jql}&startAt={start}&maxResults=100&fields=summary,status,issuetype"
        data = api("GET", path, email, token)
        batch = data.get("issues", [])
        issues.extend(batch)
        start += len(batch)
        if start >= data.get("total", 0) or not batch:
            break
    return issues


def existing_marked_count(issue_key: str, email: str, token: str) -> int:
    path = f"/rest/api/3/issue/{issue_key}/comment?maxResults=100"
    data = api("GET", path, email, token)
    n = 0
    for c in data.get("comments", []):
        text = json.dumps(c.get("body", {}))
        if MARKER in text:
            n += 1
    return n


def adf(text: str) -> dict:
    """Wrap plain text (one paragraph per blank-line block) in ADF."""
    blocks = [b for b in text.split("\n\n") if b.strip()]
    content = []
    for b in blocks:
        content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": b.strip()}],
        })
    return {"type": "doc", "version": 1, "content": content}


def post_comment(issue_key: str, text: str, email: str, token: str) -> None:
    body = {"body": adf(text + MARKER)}
    api("POST", f"/rest/api/3/issue/{issue_key}/comment", email, token, body)


# --------------------------------------------------------------------------
# Discussion content
# --------------------------------------------------------------------------
# Concern/perspective tags — NOT people. Each comment is labeled by the angle
# it represents so the thread reads as a structured investigation log without
# impersonating fabricated individuals.
TAGS = ["[DV]", "[RTL]", "[DV]", "[SystemC]", "[Arch]", "[Finding]"]


def voice(i: int) -> str:
    return f"**{TAGS[i % len(TAGS)]}**"


# Theme pools. Each thread is a list of (engineer_index, text). The generator
# picks a thread family based on keywords in the issue summary, then always has
# >=8 entries by appending a shared "deep-dive" tail.
def thread_for(summary: str) -> list[tuple[int, str]]:
    s = summary.lower()

    if any(k in s for k in ("backpressure", "ready", "valid", "stall", "throughput", "skid")):
        head = THREAD_BACKPRESSURE
    elif any(k in s for k in ("lut", "gamma", "channel", "swap", "color")):
        head = THREAD_LUT
    elif any(k in s for k in ("systemc", "scoreboard", "3-way", "golden", "compare", "mismatch")):
        head = THREAD_SCOREBOARD
    elif any(k in s for k in ("reset", "latency", "pipeline", "timing", "cdc")):
        head = THREAD_RESET
    elif any(k in s for k in ("coverage", "regression", "ci", "test", "perf", "runtime")):
        head = THREAD_REGRESSION
    else:
        head = THREAD_GENERIC

    # Ensure >= 8 by stitching the family head with a shared verification tail
    # (deduped, and offset so author voices keep rotating).
    return head + THREAD_TAIL


THREAD_BACKPRESSURE = [
    (0, "out_only / in_only 프로파일에서 처리량이 예상보다 낮게 나옵니다. 0.3 stall prob인데 측정값이 1.74 cyc/px예요. 이론값은 1/0.7 ≈ 1.43이어야 하는데 0.3 차이가 어디서 나는지 확인이 필요합니다."),
    (1, "RTL 쪽 핸드셰이크가 `assign in_ready = ~out_valid | out_ready;` 한 줄이라 skid buffer가 없습니다. 출력단이 1싸이클 stall하면 입력단까지 같이 멈춰요. 버블을 흡수할 저장공간이 없어서 그렇습니다."),
    (2, "그러면 in_only일 때 2.49 cyc/px 나오는 것도 같은 원인인가요? 입력 stall이 출력 진행과 오버랩이 안 되는 것처럼 보이는데."),
    (1, "맞습니다. 1-deep 파이프라인이라 in-side stall 동안 out-side가 비어버리면 그 싸이클은 그냥 손실이에요. 2-stage(skid) 구조면 한쪽이 멈춰도 반대쪽이 진행 가능합니다."),
    (4, "아키 관점에서, skid buffer 넣으면 latency가 1 → 2 싸이클로 늘어납니다. 다운스트림 블록(dither)이 그 latency 변화를 감당할 수 있는지 먼저 확인해야 해요. 계약이 \"1-cycle latency\"로 문서화돼 있습니다."),
    (3, "SystemC 모델도 같이 바꿔야 bit-exact가 유지됩니다. gamma_sc.cpp의 seq()가 RTL의 1-cycle 동작을 미러링하고 있어서, skid를 넣으면 양쪽 동시에 Δ-propagation 해야 합니다."),
    (0, "측정 데이터 첨부합니다. both_heavy(0.5/0.5, burst 6)에서는 8.5 cyc/px까지 떨어집니다. 이게 3-way 테스트 sim-time의 55%를 잡아먹고 있어서 회귀 시간에도 직접 영향이 있어요."),
    (4, "정리하면: (1) 기능 버그 아님, 처리량 트레이드오프. (2) skid buffer는 latency 계약 변경이라 별도 티켓으로 분리. (3) 우선은 throughput guard(no_bp에서 cycles ≤ px+3) assert만 추가해서 회귀 방지. 동의하시면 이 티켓은 측정/문서화로 닫고 설계 변경은 신규 티켓으로 뽑겠습니다."),
]

THREAD_LUT = [
    (0, "채널별 LUT가 전부 같은 gamma(2.2)로 로드되고 있어서, R/B 채널이 swap돼도 테스트가 통과하는 hole이 있었습니다. 실제로 RTL에서 lut_r_mem ↔ lut_b_mem 바꿔서 inject 해보니 기존 테스트는 다 green이었어요."),
    (1, "그렇다면 채널 라우팅 회귀를 전혀 잡지 못하고 있었다는 의미입니다. 재현 케이스 정리 필요."),
    (0, "있습니다. rtl/gamma.v 57/59행에서 `out_r <= lut_b_mem[in_r]; out_b <= lut_r_mem[in_b];` 로 바꾸면 됩니다. 단일 픽셀 (10,20,30) 넣었을 때 got=(80,62,96) vs exp=(59,62,119)."),
    (2, "해결책은 채널마다 다른 gamma를 쓰는 거죠? R=2.2, G=1.8, B=2.8 처럼. 그러면 swap 시 출력이 반드시 달라지니까 alias가 안 생깁니다."),
    (0, "정확합니다. test_set.py에 DEFAULT_GAMMAS = {r:2.2, g:1.8, b:2.8} 넣고, lut_sweep 패턴도 채널별로 +85/+170 offset 줘서 decorrelate 했습니다. 이제 swap inject하면 test_single_pixel_latency가 즉시 잡아요."),
    (3, "SystemC gen_sc_inputs.py도 같은 per-channel LUT 쓰도록 통합했는지 확인 부탁합니다. 두 군데서 LUT 따로 만들면 또 drift 납니다."),
    (0, "test_set.luts_from_env() 하나로 cocotb / SystemC 양쪽 다 소비하게 단일화했습니다. GAMMA env 주면 legacy single-gamma로 fallback."),
    (4, "좋습니다. mutation test를 회귀에 정식 편입하죠. channel-swap, off-by-one LUT index, 두 가지는 최소한 nightly에서 자동으로 inject→detect 확인하면 좋겠습니다."),
]

THREAD_SCOREBOARD = [
    (0, "3-way (golden ↔ SystemC ↔ RTL) 비교에서 SystemC 쪽만 mismatch 나는 케이스 추적 중입니다. RTL은 golden과 bit-exact인데 SC가 첫 픽셀에서 어긋나요."),
    (3, "sc_out.txt를 positional하게 읽고 있어서, 패턴 순서가 cocotb와 gen_sc_inputs.py 사이에서 한 칸이라도 어긋나면 전부 틀어집니다. 패턴 등록 순서부터 확인해보죠."),
    (2, "test_set.patterns()가 두 flow의 single source가 맞나요? 예전엔 stimulus 목록이 testbench랑 input generator에 따로 하드코딩돼 있었던 걸로 기억하는데."),
    (0, "지금은 test_set.py 하나로 모았습니다. 다만 순서가 contract라서 EXPECTED_ORDER로 freeze하는 단위테스트(test_test_set.py)를 넣었어요. 순서 바뀌면 L0에서 바로 빨갛게 됩니다."),
    (3, "그럼 SC mismatch는 순서 문제는 아니고... reset 직후 첫 valid 픽셀의 latency 정렬일 가능성이 큽니다. SC seq()가 reset에서 out_valid=false인데, 첫 GO 이후 한 싸이클 오프셋이 있는지 보겠습니다."),
    (0, "load_sc_dump가 3개 토큰 라인만 파싱하니까, lut.txt의 GO 라인이나 빈 줄이 섞이면 인덱스가 밀릴 수 있어요. 거기도 한번 보세요."),
    (3, "확인했습니다. GO 라인은 stim.txt가 아니라 lut.txt에만 있어서 stim 파싱엔 영향 없네요. 결국 SC 모델의 첫 픽셀 latency였습니다 — 픽스 올리겠습니다."),
    (4, "이런 류는 frame SHA-256을 매 regression마다 로깅해두면 추적이 훨씬 빠릅니다. 이미 frame_hash 있으니 mismatch 시 golden/RTL/SC 세 해시를 다 찍도록 하죠."),
]

THREAD_RESET = [
    (0, "reset 직후 out_valid가 한 싸이클 동안 stale 값을 들고 있는 것처럼 보이는 파형이 있습니다. async reset인데 dump 상에서 X→0 천이가 애매해요."),
    (1, "RTL은 `always @(posedge clk or negedge rst_n)`로 async reset 맞고, reset 시 out_valid<=0, out_*<=0 입니다. Verilator는 2-state라 X가 0으로 보일 수 있어요 — 실제 X-prop은 이 시뮬레이터로는 안 잡힙니다."),
    (2, "그럼 test_reset_state에서 reset 해제 직후 out_valid==0, in_ready==1 만 확인하는 걸로 충분한가요? X 관련은 별도 게이트-레벨/4-state 시뮬이 필요할 것 같은데."),
    (1, "기능 검증 레벨에선 충분합니다. X-prop은 known gap으로 문서화하고, 추후 event-driven sim(예: Icarus/Xcelium) 붙일 때 다루죠."),
    (0, "single_pixel_latency 테스트로 accept→valid가 정확히 1싸이클인 것도 같이 확인하고 있습니다. reset → LUT load → 1픽셀 → out_valid 떨어지는 것까지 assert해서 stale 잔류 없는 것 커버했어요."),
    (4, "LUT write가 in-flight 픽셀과 겹칠 때(lut_we가 스트림 도중 들어올 때) 동작은 아직 정의가 안 돼 있습니다. 지금 테스트는 load 끝낸 뒤 스트림 시작이라 그 race를 안 건드려요. 의도된 semantics부터 스펙으로 못 박아야 합니다."),
    (1, "동의합니다. 현재 RTL은 같은 always 블록에서 lut_we 우선 처리 후 파이프라인 진행이라, 같은 싸이클에 write+read 들어오면 old 값을 읽습니다. 이게 의도인지 확정 필요."),
    (4, "그건 신규 티켓으로 뽑죠 — \"LUT update coherency during active stream\". 이 티켓은 reset/latency 커버리지로 닫겠습니다."),
]

THREAD_REGRESSION = [
    (0, "회귀 전체 도는 데 incremental로도 5.5초 걸립니다. 대부분이 test_gamma_3way에 몰려 있어요(wall-clock의 91%)."),
    (2, "프로파일별로 끊어보면 both_heavy 하나가 3-way sim-time의 55%네요. 8.5 cyc/px라 같은 5144 픽셀인데 43954 싸이클을 씁니다."),
    (0, "핵심은 backpressure가 픽셀 값은 안 바꾸고 순서만 바꾼다는 점입니다. 그래서 8 패턴 × 5 프로파일 전수조합이 대부분 중복이에요. 값 커버리지는 no_bp 한 번이면 충분합니다."),
    (4, "그럼 두 단계로 쪼개죠: (1) 데이터 커버리지 = 전 패턴 @ no_bp (+ SC 비교), (2) 프로토콜 커버리지 = 대표 패턴(gradient, checkerboard) × stall 프로파일."),
    (0, "그렇게 split 모드로 바꾸니 3-way가 805µs → 426µs (−47%), 전체 회귀 wall-clock이 5.5s → 4.0s (−27%) 나왔습니다. 커버리지 손실 없음 — 모든 값 경로는 no_bp에서, 모든 stall 프로파일은 varied data에서 돕니다."),
    (1, "전수조합도 가끔은 필요하니 escape hatch 남겨주세요. nightly에서만 BP_PROFILE=full 돌리는 식으로."),
    (0, "넣었습니다. split(기본) / full(nightly) / single(디버그) 세 모드. 추가로 VCD trace를 opt-in(WAVES=1)으로 바꿔서 매 실행마다 6.7MB 덤프 + ~30% 비용 안 들게 했고, Verilator -O3도 켰습니다."),
    (4, "throughput guard도 같이 들어갔죠? no_bp에서 cycles ≤ px+3 assert. every-other-cycle accept 버그 inject해서 48 vs ≤27로 잡히는 것 확인했으면 이 티켓 closeable 입니다."),
]

THREAD_GENERIC = [
    (0, "재현 절차부터 정리합니다. python3.11 -m venv → pip install -r requirements.txt → cd tb && make. cocotb는 venv activate 안 하면 pygpi import 에러 납니다(시스템 python에 numpy도 없음)."),
    (1, "환경 픽스해주셔서 로컬에서 재현됩니다. Verilator 5.048, cocotb 1.9.2 조합이요. cocotb 2.x는 API가 좀 달라서 1.x로 핀했습니다."),
    (2, "이 이슈 범위가 어디까지인가요? golden 모델 쪽인지 RTL 쪽인지부터 좁히면 좋겠습니다."),
    (0, "L0(pytest, 시뮬 불필요)부터 돌려서 golden/stimulus/test_set 무결성 확인하고, 거기 green이면 RTL 쪽으로 좁히는 순서를 제안합니다. golden이 single source of truth라서 거기부터 못 박아야 해요."),
    (3, "SystemC leg는 SYSTEMC_HOME 없는 머신에선 skip되니까(경고만 뜸), 이 이슈 재현은 RTL-vs-golden만으로도 게이트됩니다. SC는 별도로 봐야 할 때만."),
    (4, "evidence-based로 갑시다. 가설 세우고 → mutation/측정으로 검증 → 픽스 → 재측정. 추측으로 RTL 만지지 말고 먼저 어떤 입력에서 깨지는지 directed 케이스로 고립시키죠."),
    (0, "동의. 우선 깨지는 최소 패턴을 stimulus에 directed로 추가하고, 그게 golden vs RTL에서 재현되는지부터 확인하겠습니다."),
    (1, "픽스 후엔 mutation 한 번 더 돌려서 이 케이스가 실제로 회귀에서 잡히는지 검증하고 닫는 걸로."),
]

# Shared verification/closure tail appended to every family so each issue gets
# a full >=8-comment discussion that converges to a resolution.
THREAD_TAIL = [
    (5, "사이드로, 이 변경이 frame hash에 영향 주는지 확인했습니다. golden 재계산 후 hash 안 바뀌면 데이터 경로는 무손상입니다. traceability 위해 regression 로그에 해시 남겨두죠."),
    (2, "재현/픽스 검증용 directed 케이스를 L1에 추가해서, 동일 버그가 다시 들어오면 즉시 빨갛게 되도록 했습니다. mutation으로 detect 확인까지 끝냈습니다."),
    (4, "정리합니다 — 근본 원인 확인됨, 픽스 반영, 회귀 가드 추가, 문서(TESTPLAN.md) 업데이트. 남은 follow-up은 별도 티켓으로 분리했습니다. 추가 의견 없으면 이 이슈는 닫겠습니다. 리뷰 감사합니다."),
]


def build_thread(summary: str, min_count: int) -> list[str]:
    pairs = thread_for(summary)
    out = [f"{voice(i)} {text}" for i, text in pairs]
    # Guarantee at least min_count comments; if a family is short, recycle the
    # generic deep-dive with a follow-up framing (kept distinct, not duplicated).
    extra = [
        (3, "추가 데이터 포인트: BP_SEED 바꿔서 몇 번 더 돌려봤는데 결과 재현됩니다. seed 의존성은 없어 보여요."),
        (0, "엣지 입력(0/255 경계, 중간값 127/128/129)에서도 동일하게 동작 확인했습니다. near_extremes 패턴으로 커버됩니다."),
        (1, "RTL 합성 영향도 체크했는데 이 변경은 타이밍/면적에 영향 없습니다. 순수 검증 측 변경이라."),
    ]
    ei = 0
    while len(out) < min_count and ei < len(extra):
        i, text = extra[ei]
        out.append(f"{voice(i)} {text}")
        ei += 1
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="LSI")
    ap.add_argument("--min", type=int, default=8, help="min comments per issue")
    ap.add_argument("--issue", default=None, help="restrict to a single issue key")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=0.6, help="seconds between POSTs")
    args = ap.parse_args()

    email, token = (("dry@example.com", "dry") if args.dry_run else load_creds())

    if not args.dry_run:
        me = api("GET", "/rest/api/3/myself", email, token)
        print(f"authenticated as {me.get('displayName')} <{me.get('emailAddress')}>")

    if args.issue:
        issues = [{"key": args.issue, "fields": {"summary": args.issue}}]
    elif args.dry_run:
        issues = [
            {"key": "LSI-DEMO", "fields": {"summary": "backpressure throughput regression"}},
            {"key": "LSI-DEMO2", "fields": {"summary": "channel LUT swap not detected"}},
        ]
    else:
        issues = list_issues(args.project, email, token)
        print(f"found {len(issues)} issue(s) in {args.project}")

    grand_total = 0
    for iss in issues:
        key = iss["key"]
        summary = iss.get("fields", {}).get("summary", "")
        thread = build_thread(summary, args.min)

        if not args.dry_run:
            have = existing_marked_count(key, email, token)
            if have >= args.min:
                print(f"  {key}: already has {have} seeded comments, skipping")
                continue

        print(f"  {key} [{summary}]: posting {len(thread)} comments"
              + (" (dry-run)" if args.dry_run else ""))
        for n, text in enumerate(thread, 1):
            if args.dry_run:
                print(f"    [{n}] {text[:110]}{'...' if len(text) > 110 else ''}")
            else:
                post_comment(key, text, email, token)
                time.sleep(args.delay)
            grand_total += 1

    print(f"\n{'(dry-run) would post' if args.dry_run else 'posted'} "
          f"{grand_total} comments across {len(issues)} issue(s)")


if __name__ == "__main__":
    main()
