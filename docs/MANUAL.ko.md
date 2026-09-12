# 사용자 매뉴얼 — Gamma Verification Workbench

## 지금 보고 있는 것

이 워크벤치는 하나의 질문에 답하려고 존재합니다: **이 RTL이 정말 맞는가?**

에이전트는 그럴듯한 Verilog를 쓸 수 있지만 그것을 검사하지는 못합니다. 그래서 이
프로젝트는 독립적이고 실행 가능한 참조 — Python 골든 모델 — 을 두고, 각 표현을
패턴 단위로 SHA-256 프레임 해시와 함께 대조해 증명합니다.

UI의 모든 것은 그 주장에 대한 **증거**이거나 증거를 더 만드는 **도구**입니다. 초록색
숫자가 요점이 아니라, 그 뒤의 해시가 요점입니다.

### 하나의 규칙

> **skip된 단계는 통과가 아니라 증거가 없는 것입니다.**

이 규칙은 sign-off 판정, SystemC 열, 에이전트 답변 어디에나 적용됩니다. `skip`이
보이면 무엇이 실행되지 않았는지 확인하고, 그것이 중요한지 판단하세요.

---

## 실행

```sh
# 최초 1회
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt api/requirements.txt

# 서버 (빌드된 UI도 함께 서빙합니다)
uvicorn api.server:app --host 127.0.0.1 --port 8012
```

<http://127.0.0.1:8012> 을 엽니다.

UI를 수정하며 작업하려면 Vite 개발 서버를 함께 띄우세요. `/api`를 8012로
프록시합니다:

```sh
cd frontend && npm install && npm run dev
```

### 필요한 도구

| 도구 | 용도 | 없을 때 |
|---|---|---|
| Python 3.10+, `cocotb<2.0` | 회귀 | 아무것도 동작하지 않음 |
| **Verilator ≥ 5.0** | 시뮬레이션, lint | 스코어보드가 번들 스냅샷으로 대체됨 |
| **yosys** | QoR, schematic, LEC | 해당 뷰가 *unavailable* 표시 (실패가 아님) |
| **SymbiYosys** (`sby`) + 솔버 | 게이트의 formal 단계 | 그 단계가 **skip** — 통과가 아니라 증거 없음 |
| Icarus Verilog | 4-state 교차 확인 | X/Z·리셋 초기화를 확인할 수 없음 |
| SystemC 2.3.x | SystemC 단 | 해당 열이 **skipped** |
| Hermes Gateway | Assistant, Planner | 해당 기능만 503, 나머지는 정상 |

어느 것도 나머지의 필수 의존성이 아닙니다. 도구가 없으면 **그 뷰 하나만** 기능이
줄고, 줄었다는 사실을 표시합니다.

---

## 화면 구성

```
┌──────────────────────────────────────────────────────────────┐
│ 메뉴바              File · View · Run · Help                 │
├──────────────────────────────────────────────────────────────┤
│ 툴바                Reload · Waveform · Schematic · Sign-off │
├───────────┬──────────────────────────────────┬───────────────┤
│ 설계       │  뷰 탭                            │ 속성          │
│ 탐색기     │  ────────────────────────────    │ (인스펙터)     │
│           │  작업 영역                        │               │
├───────────┴──────────────────────────────────┴───────────────┤
│ Transcript — 모든 동작을 severity 태그와 함께 기록             │
├──────────────────────────────────────────────────────────────┤
│ 상태바   설계 · 스코어보드 · QoR · 프로파일 · kb               │
└──────────────────────────────────────────────────────────────┘
```

**설계 탐색기(좌)** 는 설계를 둘러봅니다 — 모듈과 포트, 세 가지 모델 표현, 13개
테스트 패턴, 에이전트 skill. 무언가를 고르면 **오른쪽에 설명**이 뜨고, 뷰가 바뀌지는
않습니다.

**속성(우)** 은 선택된 대상의 인스펙터입니다. 탐색기에서 고르거나 schematic의 셀을
클릭하면 채워집니다.

**Transcript(하)** 는 툴 로그입니다. 모든 동작이 배너·결과·판정을 상용 툴의 메시지
형식으로 남깁니다:

```
ERROR-[LATCH] gamma.lut_rd: inferred latch — incomplete branch
    rtl/gamma.v:118
```

필터는 **임계값** 방식입니다. `W`를 누르면 경고 **이상**이 보입니다. 텍스트 상자는
태그나 내용으로 거릅니다. **복사**는 필터된 내용을 클립보드에 넣습니다 — 실패를
남에게 전달하는 가장 빠른 방법입니다.

### 크기 조절

패널은 유동적이고 구분선은 드래그할 수 있습니다. **구분선을 더블클릭**(또는 Enter)
하면 자동 크기로 돌아갑니다. 레이아웃이 이상해 보이면 **View ▸ Reset layout** 이
저장된 크기를 모두 지웁니다.

View 메뉴에서 각 독을 켜고 끄거나, 어두운/밝은 테마와 **한/영**을 전환할 수 있습니다.

---

## 각 뷰

### Overview
주장, 라이브 상태가 표시된 증명 사슬, 증거가 **다루지 못하는 것**, 설계의 핵심 사실.
여기서 시작하세요.

### Scoreboard
핵심 증거입니다. 패턴별로 golden / RTL / SystemC 프레임 해시와 일치 여부를 보여줍니다.
행을 클릭하면 오른쪽에서 자세히 볼 수 있습니다.

아래의 유의사항을 읽으세요. 회귀는 **2-state인 Verilator**에서 돌아갑니다 — 이
해시들은 이 패턴들에 대한 값 일치를 증명하며, X 전파나 리셋 초기화에 대해서는 아무
말도 하지 않습니다.

`— skipped`로 표시된 SystemC 해시는 `build/sc_out.txt`가 없었다는 뜻입니다. 증거가
없는 것이고, RTL-vs-golden 비교는 그대로 게이트했습니다.

### Waveform
`tb/dump.vcd`에 대한 Verdi/SimVision 스타일 뷰어입니다.

- 캔버스를 **클릭**하면 커서가 놓이고, 오른쪽 열에 그 시점의 모든 신호 값이 나옵니다.
- **⌘/Ctrl + 휠**로 포인터 기준 확대. **Fit**으로 전체 복귀.
- **Re-simulate**는 파형 기록 회귀를 실행합니다(`make -C tb WAVES=1`, 기록 없는
  실행보다 약 30% 느림).
- Elaboration 파라미터(`LUT_DEPTH`, `CH_R` 등)는 그리지 않고 아래에 **목록**으로
  보여줍니다 — 상수이지 파형이 아니기 때문입니다.

FIFO 내부 상태(`count`, `rd_ptr`, `wr_ptr`, `push`, `pop`)가 기록되어 있어, 핸드셰이크
질문을 추론이 아니라 여기서 답할 수 있습니다.

### Schematic
`yosys proc + opt_clean`으로 얻은 RTL 넷리스트입니다. 게이트가 아니라 **RTL 수준
셀**(`MUX`, `DFF`, `MEM rd`)인데, 이 설계의 게이트 넷리스트는 수천 개 노드라 읽을 수
없기 때문입니다.

셀은 레벨별로 좌→우 배치되고, 순차 셀이 피드백을 끊기 때문에 순환 FIFO를 가진 설계가
직선으로 읽힙니다. **셀을 클릭**하면 크로스프로빙됩니다 — 속성에 타입·폭·소스 라인이
뜨고 연결된 net이 강조됩니다.

### Quality
결정적 QoR 점수(0-100)와 설계 규칙 표입니다. **Verilog-2001 기준으로 보정**되어
있어서 `reg`/`wire`/`always @`에 감점하지 않습니다 — 이 프로젝트에서 그 방언은
실수가 아니라 의도된 선택입니다.

### Sign-off
단계: **lint → design → synthesize → simulate**. `simulate`는 mock이 아니라 실제
cocotb 3-way 회귀이며 몇 초 걸립니다.

| 판정 | 의미 |
|---|---|
| `SIGNED_OFF` | 모든 게이팅 단계 통과 |
| `CONDITIONAL` | 게이팅이 아닌 이슈가 남음 |
| `REJECTED` | 게이팅 단계 실패 |

실행 기록은 `runs/`에 쌓이고, 스파크라인이 점수 추이를 보여줍니다.

### Flows
단계 사다리에 포함되지 않는 네 가지 분석입니다.

- **Progressive-coding oracle** — 표현 × 패턴 등가 행렬을 실제로 실행합니다.
- **Adaptive reflection** — 실패가 주어졌을 때 어느 단계가 근본 원인인지 판정합니다
  (결정적, LLM 없음).
- **Equivalence (LEC)** — yosys 순차 등가성. 후보 RTL을 붙여 넣으면 프로젝트 RTL과
  같은지 증명하고, 비워 두면 자기 등가성 확인입니다.
- **Graph RAG** — 심볼의 지식 그래프 이웃을 보여줍니다.

### Improve
자기 개선 루프입니다: **제안 → 증명 → reflect → 재시도**, 횟수 제한.

`PROVEN` 판정이 **무엇을 의미하고 무엇을 의미하지 않는지**를 맨 위에 둡니다. 루프를
정직하게 유지하는 것은 그것뿐이기 때문입니다 — RTL을 고치고 스스로 채점하는
에이전트는 그럴듯함으로 수렴하므로, 여기서는 **모델이 아니라 oracle이 판정**합니다.

- **증거 공백** — 순위화, 결정적, 게이트웨이 불필요. 이미 전부 통과 중일 때 "다음에
  뭘 개선할까"의 정직한 답입니다. 다음 단계는 대개 RTL이 아니라 증거입니다.
- **Prove committed RTL** — `rtl/gamma.v`에 대해 게이트를 실행합니다: lint → design
  → synthesize → 실제 cocotb 회귀 → **formal**. LLM은 어디에도 없습니다.
  formal 단계가 있는 이유는 시뮬레이션에 **측정된 맹점**이 있기 때문입니다. FIFO
  깊이가 8 대신 7이 되는 변경은 13/13 패턴을 통과하고 처리율 차이도 0.0%인데,
  `a_no_false_stall`이 1초 안에 거부합니다.
- **Run loop** — 목표에 대한 후보를 생성하고 게이트를 통과시키며, 거부되면 **정확한
  불일치**(패턴, 픽셀 인덱스, RTL 값 vs 골든 값)를 다음 시도에 넘깁니다.

결과는 일부러 불리언이 아닙니다:

| 결과 | 의미 |
|---|---|
| `PROVEN_CHANGE` | **변경된** RTL이 골든 모델과 bit-exact |
| `ORACLE_CONFLICT` | 목표를 구현한 시도가 모두 값에서 거부됨 — 목표가 골든 모델과 모순 |
| `NO_CHANGE` | 커밋된 RTL 그대로 끝남; 목표 미구현 |
| `EXHAUSTED` | 예산 소진, 증명된 후보 없음 |

`ORACLE_CONFLICT`가 중요합니다. 새 동작이 정말 의도한 것이라면 **골든 모델을 먼저
바꿔야 합니다.** RTL은 올바름을 재정의하는 자리가 아닙니다.

`rtl/`에는 아무것도 쓰지 않습니다. 증명된 후보는 `build/improve/`에 놓이고,
**Apply**가 승격시킵니다 — 적용 전에 다시 증명하고, 현재 RTL을 백업합니다.

### Knowledge
에이전트가 근거로 받는 내용을 검색 점수와 함께 보여줍니다. 질문을 입력하고
**Retrieve**를 누르세요.

이 뷰가 존재하는 이유는 구체적입니다. 에이전트 답이 틀렸을 때 **검색이 놓친 것인지
모델이 틀린 것인지** 알아야 하는데, 이 둘은 원인도 해법도 다릅니다. 같은 질문으로
여기서 검색해 보세요.

검색은 임베딩이 아니라 어휘 기반(BM25)입니다. 질의가 `in_ready`, `FIFO_DEPTH` 같은
식별자이고 벡터 유사도는 바로 그것을 뭉개기 때문입니다. 한글 질문은 도메인 용어집으로
연결됩니다.

### Assistant
**Plan** 은 명세 변경을 태그된 단계로 바꿉니다. `docs/UARCH.md` 전체가 입력으로
전송되고, 사용자는 **CHANGED** 델타만 편집합니다. 각 단계에 `NEW` / `MODIFIED` /
`UNCHANGED` 태그가 붙어 점진적 재생성이 움직인 부분만 건드립니다.

**Ask** 는 RTL 어시스턴트입니다. 모든 답변에 근거가 된 구절이 함께 옵니다 —
*"grounded in N passages"* 를 펼쳐 답을 출처와 대조하세요.

한글로 쓰면 한글로 답합니다.

---

## 자주 하는 작업

**설계가 여전히 동작하는지 증명하기.**
툴바 ▸ Run sign-off. 또는 `./scripts/run_3way.sh`.

**핸드셰이크 문제 조사하기.**
Waveform ▸ Re-simulate 후, 관심 있는 시점에 커서를 놓고 `in_ready`, `count`,
`out_valid`를 함께 읽으세요.

**신호가 어디서 구동되는지 찾기.**
Schematic에서 셀을 클릭하면 속성에 `rtl/gamma.v:<line>` 이 나옵니다.

**정밀도나 FIFO 깊이 변경하기.**
Δ-propagation 드릴입니다 — 세 파일이 함께 움직여야 합니다. `docs/UARCH.md` §7 참고.
그리고 sign-off를 다시 실행하세요. 깊이 변경(타이밍 전용)이면 해시가 그대로여야
하고, 정밀도 변경이면 해시가 **바뀌어야** 합니다.

**다음에 뭘 할지 정하기.**
Improve ▸ 증거 공백을 읽으세요. 스코어보드가 실제로 증명하는 범위를 얼마나 넓히는지
기준으로 순위가 매겨져 있습니다.

**에이전트가 무엇을 아는지 확인하기.**
Knowledge ▸ 질문 입력 ▸ Retrieve. 아무것도 안 나오면 에이전트는 고정 컨텍스트만으로
답하게 되므로, 출처 추가를 고려하세요.

**실패를 다른 사람에게 전달하기.**
Transcript ▸ 임계값을 `W`로 ▸ 복사.

---

## 이상해 보일 때

| 증상 | 원인 | 해결 |
|---|---|---|
| Assistant가 503 | 게이트웨이 키 없음 | `.env`에 `HERMES_GATEWAY_API_KEY` 설정 |
| 툴바에 `skills 2/6` | 서빙 프로파일에 skill 없음 | `python scripts/sync_hermes_skills.py` |
| 상태바에 예상 밖 프로파일 | 다른 에이전트가 8643 점유 | `lsof -nP -iTCP:8643 -sTCP:LISTEN` |
| Schematic이 unavailable | yosys가 PATH에 없음 | yosys 설치 |
| Waveform에 덤프 없음 | 기록한 적 없음 | Re-simulate 또는 `make -C tb WAVES=1` |
| SystemC 열이 전부 skip | `build/sc_out.txt` 없음 | SystemC 시뮬 빌드 (README 참고) |
| formal 단계가 skip | `sby`가 PATH에 없음 | SymbiYosys 설치 |
| 스코어보드가 오래되어 보임 | 백엔드 연결 불가 | `public/results.json`으로 대체된 것, 서버 확인 |
| 패널이 깨져 보임 | 저장된 패널 크기 | View ▸ Reset layout |
| cocotb가 Python 오류로 실패 | `PYTHONHOME` 오염 | `make` 전에 venv 활성화 |

---

## 명령줄 대응표

```sh
./scripts/run_3way.sh                   # 전체 회귀
python -m pytest tests/ -q              # L0 유닛 테스트, 시뮬레이터 불필요
cd tb && make                           # L1+L2, verilator
cd tb && make SIM=icarus                # 4-state 교차 확인
cd tb && make WAVES=1                   # VCD 포함
cd tb && make TESTCASE=test_lut_reload  # 테스트 하나만
BP_PROFILE=full make -C tb              # 모든 패턴 × 프로파일 (야간)
sby -f formal/gamma.sby bmc             # formal (bounded)
sby -f formal/gamma.sby cover           # 도달 가능성 (공허하지 않음 확인)

curl localhost:8012/api/verification     # 스코어보드
curl localhost:8012/api/skills           # 에이전트가 로드할 수 있는 skill
curl "localhost:8012/api/kb/search?q=in_ready"   # 에이전트가 받을 근거
curl localhost:8012/api/improve/audit    # 증거 공백
python scripts/sync_hermes_skills.py --list      # skill 설치 상태
cd frontend && npm run check:responsive          # 레이아웃 게이트
```

---

## 더 읽을 것

- **[`README.md`](../README.md)** — 이 프로젝트가 왜 존재하는가
- **[`docs/UARCH.md`](UARCH.md)** — 마이크로아키텍처 명세
- **[`TESTPLAN.md`](../TESTPLAN.md)** — 테스트 계층, 커버리지 근거, 그리고 알려진
  공백을 있는 그대로
- **[`CLAUDE.md`](../CLAUDE.md)** — 기여자를 위한 저장소 규약
