import { createContext, useContext } from 'react'

/**
 * Korean / English UI text.
 *
 * Two deliberate choices:
 *
 * 1. **Keys are the English source string**, not symbolic ids. A missing
 *    translation then renders as English instead of `overview.thesis.claim`,
 *    so an incomplete dictionary degrades into a usable tool rather than a
 *    broken one — and the English copy stays readable in the source.
 *
 * 2. **Technical vocabulary is not translated.** Signal names (`in_ready`),
 *    stage names (`lint`, `synthesize`), verdicts (`PROVEN`, `SIGNED_OFF`),
 *    units (`cyc/px`) and view names stay as they are. They are the same tokens
 *    the CLI prints, the transcript logs and the documents use; translating them
 *    would break that correspondence and make the tool harder to use, not
 *    easier. What gets translated is the prose that explains them.
 */

export type Lang = 'en' | 'ko'

const KO: Record<string, string> = {
  // Product shell and evidence dashboard
  "Overview": "개요",
  "Scoreboard": "스코어보드",
  "Quality": "설계 품질",
  "Sign-off": "Sign-off",
  "Flows": "검증 흐름",
  "Improve": "개선",
  "Knowledge": "지식 검색",
  "Assistant": "어시스턴트",
  "Manual": "매뉴얼",
  "Workspace": "워크스페이스",
  "Verification": "검증",
  "Intelligence": "인텔리전스",
  "Resources": "리소스",
  "Your design, verification evidence, and next steps at a glance.": "설계 상태, 검증 증거, 다음 작업을 한눈에 확인하세요.",
  "Compare every pattern against the independent golden model.": "독립적인 골든 모델을 기준으로 모든 패턴을 비교합니다.",
  "Inspect signal timing and ready/valid handshakes.": "신호 타이밍과 ready/valid 핸드셰이크를 확인합니다.",
  "Explore the elaborated RTL and its connections.": "생성된 RTL 회로와 연결 관계를 살펴봅니다.",
  "Review synthesis metrics, lint findings, and design rules.": "합성 지표, lint 결과, 설계 규칙을 검토합니다.",
  "Run the verification ladder and inspect each stage of evidence.": "검증 단계를 실행하고 각 단계의 증거를 확인합니다.",
  "Prove equivalence, trace failures, and inspect the proof chain.": "등가성을 증명하고 실패 원인과 검증 과정을 추적합니다.",
  "Find gaps in evidence and evaluate design improvements.": "검증 증거의 부족한 부분을 찾고 설계 개선안을 평가합니다.",
  "Search project knowledge with traceable source passages.": "출처를 확인할 수 있는 프로젝트 지식을 검색합니다.",
  "Plan design changes and ask questions grounded in your project.": "설계 변경을 계획하고 프로젝트에 근거한 답변을 받아보세요.",
  "Everything you need to work confidently with Gamma.": "Gamma를 활용하는 데 필요한 내용을 확인하세요.",
  "Skip to content": "본문으로 이동",
  "Workspace navigation": "워크스페이스 탐색",
  "Main navigation": "주요 메뉴",
  "Open navigation": "메뉴 열기",
  "Close navigation": "메뉴 닫기",
  "RTL verification project": "RTL 검증 프로젝트",
  "Evidence you can inspect.": "직접 확인할 수 있는 검증 증거",
  "Every pattern. Every representation.": "모든 패턴과 구현을 검증합니다.",
  "Documentation": "문서",
  "Search workspace…": "워크스페이스 검색…",
  "Search workspace": "워크스페이스 검색",
  "Search pages, patterns, and actions…": "화면, 패턴, 작업 검색…",
  "Search results": "검색 결과",
  "Close search": "검색 닫기",
  "Inspect test pattern": "테스트 패턴 확인",
  "Refresh verification results and project status.": "검증 결과와 프로젝트 상태를 갱신합니다.",
  "No matches. Try a page name or test pattern.": "검색 결과가 없습니다. 화면 이름이나 테스트 패턴을 입력해 보세요.",
  "navigate": "이동",
  "open": "열기",
  "close": "닫기",
  "Backend connected": "백엔드 연결됨",
  "Live tools unavailable": "실시간 도구 사용 불가",
  "Live": "연결됨",
  "Offline": "오프라인",
  "Refresh": "새로고침",
  "Design": "설계",
  "Inspector": "속성 패널",
  "Export results": "결과 내보내기",
  "Saved snapshot": "저장된 스냅샷",
  "Loading view…": "화면을 불러오는 중…",
  "Verification results are unavailable.": "검증 결과를 불러올 수 없습니다.",
  "Retry": "다시 시도",
  "You are viewing a saved snapshot.": "저장된 스냅샷을 보고 있습니다.",
  "Live verification and tool status will return when the backend reconnects.": "백엔드에 다시 연결하면 최신 데이터와 도구 상태를 확인할 수 있습니다.",
  "Reconnect": "다시 연결",
  "VERIFICATION STATUS": "검증 상태",
  "REFERENCE MODEL": "기준 모델",
  "Latest results": "최신 결과",
  "Awaiting results": "결과 대기 중",
  "Expected values": "기대값",
  "Every tested pattern matches.": "모든 테스트 패턴이 일치합니다.",
  "Patterns need your attention.": "확인이 필요한 패턴이 있습니다.",
  "Your verification workspace is ready.": "검증 워크스페이스가 준비되었습니다.",
  "Your reference model is ready.": "기준 모델이 준비되었습니다.",
  "Expected hashes are available. Run sign-off to collect measured simulation evidence.": "기대 해시를 확인할 수 있습니다. Sign-off를 실행해 실제 시뮬레이션 증거를 수집하세요.",
  "of": "/",
  "patterns agree with the golden model.": "개 패턴이 골든 모델과 일치합니다.",
  "Connect your tools to start building verification evidence.": "도구를 연결하고 검증 증거를 수집하세요.",
  "Three representations, independently compared.": "세 가지 구현을 독립적으로 비교했습니다.",
  "SystemC evidence is incomplete.": "SystemC 비교 증거가 부족합니다.",
  "View scoreboard": "스코어보드 보기",
  "Project metrics": "프로젝트 지표",
  "Patterns verified": "검증된 패턴",
  "Reference patterns": "기준 패턴",
  "Expected outputs from the golden model": "골든 모델에서 계산한 기대 출력",
  "of the test set passes": "테스트 패턴 통과",
  "Awaiting verification data": "검증 데이터 대기 중",
  "Pixels compared": "비교한 픽셀",
  "Pixels in test set": "테스트 픽셀",
  "Ready for frame-level comparison": "프레임 단위 비교 준비 완료",
  "Frame-level SHA-256 comparison": "프레임 단위 SHA-256 비교",
  "Design quality": "설계 품질",
  "Grade": "등급",
  "checks passed": "개 검사 통과",
  "Quality analysis unavailable": "품질 분석 결과 없음",
  "Archived sign-offs": "저장된 Sign-off",
  "Mean score": "평균 점수",
  "Run the full ladder to collect evidence": "전체 검증을 실행해 증거를 수집하세요",
  "Gamma transfer curves": "감마 변환 곡선",
  "Independent channels. One reference model.": "독립적인 채널, 하나의 기준 모델.",
  "REFERENCE LUT": "기준 LUT",
  "Gamma correction reference curves for red, green, and blue channels": "빨강, 초록, 파랑 채널의 감마 보정 기준 곡선",
  "Input": "입력",
  "Reference equation: output = round((input / max)^(1/γ) × max).": "기준 수식: 출력 = round((입력 / 최댓값)^(1/γ) × 최댓값).",
  "Load verification results to explore the reference curves.": "검증 데이터를 불러오면 기준 곡선을 확인할 수 있습니다.",
  "Evidence at every representation.": "각 구현 단계의 검증 증거",
  "Independent executable reference": "독립적으로 실행되는 기준 모델",
  "Frame hashes compared to golden": "골든 모델과 프레임 해시 비교",
  "Missing comparison evidence": "비교 증거 없음",
  "Measured simulation required": "실제 시뮬레이션 필요",
  "Reference": "기준 모델",
  "Matched": "일치",
  "Mismatch": "불일치",
  "No evidence": "증거 없음",
  "A skipped stage is missing evidence, never a pass. 2-state simulation does not cover X/Z behavior.": "건너뛴 단계는 통과가 아닌 증거 부족입니다. 2-state 시뮬레이션은 X/Z 동작을 검증하지 않습니다.",
  "Explore verification flows": "검증 흐름 살펴보기",
  "Quick actions": "빠른 작업",
  "Inspect waveforms": "파형 확인",
  "Understand signal timing": "신호 타이밍을 분석하세요",
  "Explore schematic": "회로도 탐색",
  "Follow your design connections": "설계의 연결 관계를 확인하세요",
  "Ask the assistant": "어시스턴트에게 질문",
  "Answers grounded in your project": "프로젝트에 근거한 답변을 받아보세요",
  "Test patterns": "테스트 패턴",
  "The latest results from your comparison matrix.": "패턴 비교표의 최신 결과입니다.",
  "Reference inputs, ready for simulation.": "시뮬레이션에 사용할 기준 입력입니다.",
  "View all": "전체 보기",
  "patterns": "개 패턴",
  "Bit-exact comparison": "비트 단위 일치 비교",
  "Reference hashes": "기준 해시",
  "Per-channel gamma correction": "채널별 감마 보정",
  "LUT depth": "LUT 깊이",
  "pixel / cycle": "픽셀 / 사이클",
  "Knowledge passages": "검색 가능한 지식",
  "Active agent skills": "활성 에이전트 스킬",
  "An executable oracle. Independent implementations. Inspectable evidence.": "실행 가능한 기준 모델 · 독립적인 구현 · 확인 가능한 검증 증거",
  "How verification works": "검증 방식 알아보기",
  "Filter transcript": "Transcript 필터",
  "Reference preview": "기준값 미리보기",
  "Expected": "기대값",
  "Filter patterns…": "패턴 검색…",
  "Filter patterns": "패턴 검색",
  "All patterns": "전체 패턴",
  "Failed only": "실패한 패턴",
  "No patterns match your filters.": "조건에 맞는 패턴이 없습니다.",
  "Reset filters": "필터 초기화",
  "These are expected outputs, not measured RTL results. Run sign-off to verify the implementation.": "이 값은 기대 출력이며 실제 RTL 측정 결과가 아닙니다. Sign-off를 실행해 구현을 검증하세요.",
  "Expected golden hashes": "기대 골든 해시",
  "Not measured": "측정되지 않음",
  "Pattern comparison": "패턴 비교",
  "Sign-off could not complete. Open the transcript for details and retry.": "Sign-off를 완료하지 못했습니다. Transcript에서 원인을 확인한 후 다시 시도하세요.",
  "No sign-off run yet": "아직 Sign-off 실행 결과가 없습니다",
  "Collect evidence for your design": "설계의 검증 증거를 수집하세요",
  "Run lint, design checks, synthesis, and simulation. Each stage reports its own result.": "lint, 설계 검사, 합성, 시뮬레이션을 실행하고 각 단계의 결과를 확인합니다.",

  // ---- shell ----
  'golden model as executable oracle · 3-way bit-exact':
    '골든 모델을 실행 가능한 oracle로 · 3-way bit-exact',
  'Reload all': '전체 다시 읽기',
  'Export transcript…': 'Transcript 내보내기…',
  'Export results.json…': 'results.json 내보내기…',
  'Design navigator': '설계 탐색기',
  Properties: '속성',
  Transcript: 'Transcript',
  'Reset layout': '레이아웃 초기화',
  'Light theme': '밝은 테마',
  'Dark theme': '어두운 테마',
  'Sign-off ladder': 'Sign-off 단계 실행',
  'Traced simulation…': '파형 기록 시뮬레이션…',
  'Elaborate schematic': 'Schematic 생성',
  'Flows (LEC, reflection)…': 'Flows (LEC, reflection)…',
  'Self-improvement loop…': '자기 개선 루프…',
  'Knowledge retrieval…': '지식 검색…',
  'User manual': '사용자 매뉴얼',
  'What is this?': '이게 뭔가요?',
  About: '정보',
  connected: '연결됨',
  offline: '연결 끊김',
  Reload: '다시 읽기',
  Waveform: 'Waveform',
  Schematic: 'Schematic',
  'Run sign-off': 'Sign-off 실행',
  'Running sign-off…': 'Sign-off 실행 중…',
  'Refreshing…': '갱신 중…',
  design: '설계',
  scoreboard: '스코어보드',
  profile: '프로파일',
  model: '모델',
  updated: '갱신',
  'loading…': '읽는 중…',

  // ---- overview ----
  'An agent can write plausible RTL. It cannot tell you whether the RTL is right.':
    '에이전트는 그럴듯한 RTL을 쓸 수 있습니다. 그 RTL이 맞는지는 말해주지 못합니다.',
  'The proof chain': '증명 사슬',
  'Open scoreboard →': '스코어보드 열기 →',
  'Open schematic →': 'Schematic 열기 →',
  'Design under verification': '검증 대상 설계',
  'What the workbench adds': '이 워크벤치가 더하는 것',
  'each exists because a generate-then-hope loop lacks it':
    '생성하고 기대만 하는 루프에 없는 것들입니다',
  'defines the expected values — untimed, independent, cheap to re-run':
    '기대값을 정의합니다 — 시간 개념 없음, 독립적, 재실행이 저렴',
  'bit-exact against the oracle': 'oracle과 bit-exact',
  'skipped — build/sc_out.txt absent. Missing evidence, not a pass.':
    'skip — build/sc_out.txt 없음. 통과가 아니라 증거 없음입니다.',
  'no results loaded': '결과 없음',
  throughput: '처리율',
  latency: '레이턴시',
  handshake: '핸드셰이크',
  elasticity: '탄력성',
  precision: '정밀도',
  module: '모듈',

  // ---- honesty banners ----
  'What this does not prove.': '이것이 증명하지 못하는 것.',
  'Coverage caveat.': '커버리지 유의사항.',
  'What a PROVEN verdict means.': 'PROVEN 판정의 의미.',
  'What it does not mean.': '의미하지 않는 것.',
  'What this does not prove. The regression runs under Verilator, which is 2-state. These hashes cover value equality on the listed patterns; they do not cover X-propagation or reset-initialization behaviour. A skipped stage is missing evidence, not a pass. Cross-check with':
    '이것이 증명하지 못하는 것. 회귀는 2-state인 Verilator에서 돌아갑니다. 이 해시들은 나열된 패턴에 대한 값 일치를 다루지, X 전파나 리셋 초기화 동작은 다루지 않습니다. skip된 단계는 통과가 아니라 증거 없음입니다. 다음으로 교차 확인하세요:',

  // ---- scoreboard ----
  'Pattern Comparison Matrix': '패턴 비교 행렬',
  'scoreboard verdict': '스코어보드 판정',
  'patterns bit-exact': 'bit-exact 패턴',
  'pixels compared': '비교한 픽셀',
  'pixel width / LUT depth': '픽셀 폭 / LUT 깊이',
  'γ per channel (R·G·B)': '채널별 γ (R·G·B)',
  'Loading verification results…': '검증 결과 읽는 중…',

  // ---- quality / sign-off ----
  'Design Quality (QoR)': '설계 품질 (QoR)',
  'Design Rule Checks': '설계 규칙 검사',
  'Sign-off Ladder': 'Sign-off 단계',
  'No QoR report — reload from the toolbar.': 'QoR 리포트 없음 — 툴바에서 다시 읽으세요.',
  severity: '심각도',
  rule: '규칙',
  result: '결과',
  detail: '상세',
  stage: '단계',
  status: '상태',
  gating: '게이팅',
  pattern: '패턴',
  pixels: '픽셀',
  'score trend': '점수 추이',
  'mism.': '불일치',
  representation: '표현',
  role: '역할',
  verdict: '판정',
  'Progressive-coding oracle': '점진적 코딩 oracle',
  'Adaptive reflection': '적응형 reflection',
  'Logical equivalence (LEC)': '논리 등가성 (LEC)',
  'Graph RAG': 'Graph RAG',

  // ---- waveform / schematic ----
  'Zoom in': '확대',
  'Zoom out': '축소',
  'Zoom fit': '전체 보기',
  cursor: '커서',
  window: '구간',
  signal: '신호',
  value: '값',
  'Re-simulate': '다시 시뮬레이션',
  'Re-simulating…': '시뮬레이션 중…',
  'No waveform dump yet.': '아직 파형 덤프가 없습니다.',
  'Run traced regression': '파형 기록 회귀 실행',
  'Running traced regression…': '파형 기록 회귀 실행 중…',
  'Re-elaborate': '다시 생성',
  'Elaborating…': '생성 중…',
  cells: '셀',
  nets: '넷',
  levels: '레벨',
  parameters: '파라미터',
  input: '입력',
  output: '출력',
  flop: '플립플롭',
  memory: '메모리',
  arith: '산술',
  logic: '논리',

  // ---- knowledge ----
  'Knowledge Base': '지식 베이스',
  'Retrieved passages': '검색된 근거',
  'Index composition': '색인 구성',
  Retrieve: '검색',
  source: '출처',
  passages: '근거',
  'ask what the agent would be asked…': '에이전트에게 물을 내용을 입력하세요…',

  // ---- improve ----
  'Evidence gaps': '증거 공백',
  'what to improve next — deterministic, no gateway':
    '다음에 개선할 것 — 결정적, 게이트웨이 불필요',
  'Baseline gate': '기준선 게이트',
  'Mutation coverage': '변이 커버리지',
  mutants: '변이 수',
  'Run campaign': '캠페인 실행',
  fault: '결함',
  line: '행',
  'caught by': '검출 단계',
  'Injecting faults and running the gate': '결함 주입 후 게이트 실행 중',
  'Injects one plausible fault at a time and runs the real gate on each. A pass rate says the design agrees with the golden model on the inputs someone wrote down; this says whether the suite would notice if the design were wrong. ~10s per mutant.':
    '그럴듯한 결함을 하나씩 주입하고 각각에 실제 게이트를 돌립니다. 통과율은 누군가 적어 둔 입력에 대해 설계가 골든 모델과 일치한다는 뜻일 뿐이고, 이것은 설계가 틀렸을 때 검사 묶음이 알아차리는지를 말합니다. 변이당 약 10초.',
  'Improvement loop': '개선 루프',
  'Prove committed RTL': '커밋된 RTL 증명',
  'Proving…': '증명 중…',
  'Run loop': '루프 실행',
  'Running…': '실행 중…',
  'max iters': '최대 반복',
  gap: '공백',
  'why it matters': '왜 중요한가',
  'how to close': '메우는 방법',
  tool: '도구',
  ready: '준비됨',
  'not installed': '미설치',
  'Apply to rtl/gamma.v': 'rtl/gamma.v에 적용',
  'Applying…': '적용 중…',
  'the change you want, stated as a goal': '원하는 변경을 목표 형태로 적으세요',

  // ---- assistant ----
  'Implementation plan': '구현 계획',
  'Generate plan': '계획 생성',
  'Planning…': '계획 생성 중…',
  'Ask Hermes': 'Hermes에게 질문',
  'Clear (new session)': '지우기 (새 세션)',
  'CHANGED — the proposal': 'CHANGED — 제안 내용',
  'uArch specification (read-only input)': 'uArch 명세 (읽기 전용 입력)',
  'No plan yet — describe the uArch change and generate.':
    '아직 계획이 없습니다 — uArch 변경을 적고 생성하세요.',

  // ---- console ----
  'filter (tag or text)': '필터 (태그 또는 내용)',
  follow: '따라가기',
  Copy: '복사',
  Clear: '지우기',
  'No messages at this threshold. Run a flow from the toolbar.':
    '이 기준에는 메시지가 없습니다. 툴바에서 플로우를 실행하세요.',

  // ---- shared ----
  'Select an object in the navigator, or click a cell in the schematic.':
    '탐색기에서 객체를 고르거나 schematic의 셀을 클릭하세요.',
  Contents: '목차',
  'Loading manual…': '매뉴얼 읽는 중…',
  'Manual unavailable.': '매뉴얼을 불러올 수 없습니다.',
  'No translation for this document yet — showing the English original.':
    '이 문서의 번역본이 아직 없어 영어 원문을 보여줍니다.',
}

const DICT: Record<Lang, Record<string, string>> = { en: {}, ko: KO }

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: 'en',
  setLang: () => {},
})

export function useLang() {
  return useContext(LangContext)
}

/** Translate, falling back to the English source when nothing is registered. */
export function useT(): (en: string) => string {
  const { lang } = useLang()
  return (en: string) => DICT[lang][en] ?? en
}

export function readStoredLang(): Lang {
  try {
    const v = localStorage.getItem('wb-lang')
    if (v === 'ko' || v === 'en') return v
  } catch { /* private mode */ }
  // Follow the browser on first visit; the toggle overrides it from then on.
  return typeof navigator !== 'undefined' && navigator.language?.startsWith('ko')
    ? 'ko' : 'en'
}

export function storeLang(l: Lang) {
  try { localStorage.setItem('wb-lang', l) } catch { /* private mode */ }
}
