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
