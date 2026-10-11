import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Console } from './Console'
import { LangContext, readStoredLang, storeLang, useLang, useT } from './i18n'
import type { Lang } from './i18n'
import { Navigator } from './Navigator'
import { Overview } from './Overview'
import { Properties } from './Properties'
import { Splitter, applySavedPanes, resetPanes } from './Splitter'
import { CommandPalette } from './components/CommandPalette'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Icon } from './components/Icon'
import { downloadFile } from './download'
import { isReference } from './evidence'
import { useView } from './hooks/useView'
import { useWorkbench } from './hooks/useWorkbench'
import { formatTranscript, log } from './log'
import { NAVIGATION, type View } from './navigation'
import { readPreference, writePreference } from './storage'
import type { PatternResult, SchematicNode } from './types'

const Scoreboard = lazy(() => import('./views/Scoreboard').then(m => ({ default: m.Scoreboard })))
const Quality = lazy(() => import('./views/Quality').then(m => ({ default: m.Quality })))
const SignoffView = lazy(() => import('./views/SignoffView').then(m => ({ default: m.SignoffView })))
const Flows = lazy(() => import('./views/Flows').then(m => ({ default: m.Flows })))
const WaveformPane = lazy(() => import('./Waveform').then(m => ({ default: m.WaveformPane })))
const SchematicPane = lazy(() => import('./Schematic').then(m => ({ default: m.SchematicPane })))
const ImprovePane = lazy(() => import('./Improve').then(m => ({ default: m.ImprovePane })))
const KnowledgePane = lazy(() => import('./Knowledge').then(m => ({ default: m.KnowledgePane })))
const HelpPane = lazy(() => import('./Help').then(m => ({ default: m.HelpPane })))
const Assistant = lazy(() => import('./views/Assistant'))

export default function App() {
  const [lang, setLangState] = useState<Lang>(readStoredLang)
  const setLang = useCallback((next: Lang) => { setLangState(next); storeLang(next) }, [])
  useEffect(() => { document.documentElement.lang = lang }, [lang])
  return <LangContext.Provider value={{ lang, setLang }}><Workbench /></LangContext.Provider>
}

function Workbench() {
  const t = useT()
  const { lang, setLang } = useLang()
  const [view, navigate] = useView()
  const { health, data, qor, skills, kb, telemetry, signoff, signoffError, sel, setSel, busy, updatedAt, loadAll, runSignoff } = useWorkbench()
  const [consoleOpen, setConsoleOpen] = useState(false)
  const [showNav, setShowNav] = useState(false)
  const [showProps, setShowProps] = useState(false)
  const [mobileNav, setMobileNav] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => readPreference('wb-theme', 'dark') === 'light' ? 'light' : 'dark')
  const shellRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLButtonElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  const page = NAVIGATION.find(item => item.id === view)!
  const gatewayReady = !!health?.has_key

  useLayoutEffect(() => { applySavedPanes(shellRef.current) }, [])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    writePreference('wb-theme', theme)
  }, [theme])
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearchOpen(open => !open) }
      if (event.key === 'Escape' && mobileNav) { setMobileNav(false); menuRef.current?.focus() }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [mobileNav])
  useEffect(() => {
    if (mobileNav) sidebarRef.current?.querySelector<HTMLAnchorElement>('a')?.focus()
  }, [mobileNav])

  function go(next: View) { navigate(next); setMobileNav(false) }
  function pick(pattern: PatternResult) { setSel({ kind: 'pattern', id: pattern.name, data: pattern }); setShowProps(true) }
  function run() { go('signoff'); void runSignoff() }
  function exportResults() { if (data) downloadFile('gamma-results.json', JSON.stringify(data, null, 2), 'application/json') }
  function exportTranscript() {
    downloadFile(`gamma-transcript-${new Date().toISOString().slice(0, 10)}.log`, formatTranscript())
    log.info('CONSOLE', 'Full session transcript exported')
  }

  return <div className="workbench" ref={shellRef}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>{t('Skip to content')}</a>
    {mobileNav && <button className="sidebar-backdrop" aria-label={t('Close navigation')} onClick={() => { setMobileNav(false); menuRef.current?.focus() }} />}
    <aside className={`app-sidebar ${mobileNav ? 'sidebar-open' : ''}`} ref={sidebarRef} aria-label={t('Workspace navigation')} onKeyDown={event => {
      if (!mobileNav || event.key !== 'Tab') return
      const links = sidebarRef.current?.querySelectorAll<HTMLElement>('a, button')
      if (!links?.length) return
      if (event.shiftKey && document.activeElement === links[0]) { event.preventDefault(); links[links.length - 1].focus() }
      else if (!event.shiftKey && document.activeElement === links[links.length - 1]) { event.preventDefault(); links[0].focus() }
    }}>
      <a className="app-brand" href="#overview" onClick={() => setMobileNav(false)} aria-label="Gamma overview"><span className="app-brand-mark">γ</span><span>gamma<span className="app-brand-sub">VERIFICATION WORKBENCH</span></span></a>
      <div className="project-switch"><span className="project-avatar"><Icon name="chip" size={20} /></span><span><strong>{data?.design.module ?? 'gamma'}</strong><small>{t('RTL verification project')}</small></span><span className="project-dot" /></div>
      <nav className="app-navigation" aria-label={t('Main navigation')}>
        {['Workspace', 'Verification', 'Intelligence', 'Resources'].map(group => <div className="app-nav-group" key={group}>
          <div className="app-nav-label">{t(group)}</div>
          {NAVIGATION.filter(item => item.group === group).map(item => <a href={`#${item.id}`} key={item.id}
            data-view={item.id} className={`app-nav-link ${view === item.id ? 'app-nav-active' : ''}`} aria-current={view === item.id ? 'page' : undefined}
            onClick={() => setMobileNav(false)}><Icon name={item.icon} /><span>{t(item.label)}</span>
            {item.id === 'scoreboard' && data && <span className="nav-link-count">{data.summary.total_patterns}</span>}
            {item.id === 'assistant' && <span className="nav-ai">AI</span>}
          </a>)}
        </div>)}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><Icon name="shield" size={18} /><span>{t('Evidence you can inspect.')}<small>{t('Every pattern. Every representation.')}</small></span></div>
        <button className="sidebar-help" onClick={() => go('help')}><Icon name="help" size={17} />{t('Documentation')}<Icon name="arrow" size={15} /></button>
        <div className="sidebar-version"><span>Gamma Workbench</span><span>v0.1</span></div>
      </div>
    </aside>
    <div className="app-main">
      <header className="app-topbar">
        <button ref={menuRef} className="icon-button mobile-menu" aria-label={t('Open navigation')} aria-expanded={mobileNav} onClick={() => setMobileNav(!mobileNav)}><Icon name="menu" /></button>
        <div className="breadcrumbs"><span>{t('Workspace')}</span><Icon name="chevron" size={13} /><span className="breadcrumb-project">{data?.design.module ?? 'gamma'}</span><Icon name="chevron" size={13} /><strong>{t(page.label)}</strong></div>
        <div className="topbar-actions">
          <button className="workspace-search" onClick={() => setSearchOpen(true)}><Icon name="search" size={16} /><span>{t('Search workspace…')}</span><kbd>⌘ K</kbd></button>
          <span className={`connection-status ${health ? 'is-online' : 'is-offline'}`} title={health ? t('Backend connected') : t('Live tools unavailable')}><i />{health ? t('Live') : t('Offline')}</span>
          <button className="icon-button theme-toggle" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={theme === 'dark' ? t('Light theme') : t('Dark theme')} title={theme === 'dark' ? t('Light theme') : t('Dark theme')}><Icon name={theme === 'dark' ? 'sun' : 'moon'} /></button>
          <button className="language-button" onClick={() => setLang(lang === 'ko' ? 'en' : 'ko')} aria-label={lang === 'ko' ? 'Switch to English' : '한국어로 전환'}>{lang === 'ko' ? 'EN' : '한'}</button>
        </div>
      </header>
      <div className="page-heading">
        <div><div className="page-eyebrow">GAMMA / {t(page.group).toUpperCase()}</div><h1>{t(page.label)}</h1><p>{t(page.description)}</p></div>
        <div className="page-actions"><button className="secondary-button refresh-button" onClick={() => void loadAll()} disabled={!!busy} title={t('Reload all')}><Icon name="refresh" size={16} className={busy === 'load' ? 'spin' : ''} /><span>{t('Refresh')}</span></button>
          <button className="primary-button" onClick={run} disabled={!!busy}><Icon name="play" size={14} />{busy === 'signoff' ? t('Running sign-off…') : t('Run sign-off')}</button></div>
      </div>
      <div className="workspace-tools"><div className="workspace-context"><Icon name="chip" size={15} /><span className="mono">rtl/gamma.v</span><span className="context-sep" /><span>{data ? `${data.design.pixel_w}-bit` : '8-bit'} · Verilog-2001</span>{data?.resultMode === 'snapshot' && <span className="snapshot-tag">{t('Saved snapshot')}</span>}</div>
        <div className="workspace-tool-actions"><button className={showNav ? 'is-active' : ''} onClick={() => setShowNav(!showNav)} aria-pressed={showNav} title={t('Design navigator')}><Icon name="folder" size={16} /><span>{t('Design')}</span></button><button className={showProps ? 'is-active' : ''} onClick={() => setShowProps(!showProps)} aria-pressed={showProps} title={t('Properties')}><Icon name="panel" size={16} /><span>{t('Inspector')}</span></button><button onClick={exportResults} disabled={!data} title={t('Export results')} aria-label={t('Export results')}><Icon name="download" size={16} /></button></div>
      </div>
      <div className="workspace">
        {showNav && <><Navigator data={data} skills={skills} selected={sel} onSelect={selection => { setSel(selection); setShowProps(true) }} /><Splitter axis="x" varName="--nav-w" min={150} max={360} label="Navigator width" /></>}
        <main className="work-area" id="main-content" tabIndex={-1} aria-label={t(page.label)}>
          <div className="view-body"><ErrorBoundary key={view}><Suspense fallback={<div className="pane-empty" role="status"><i className="spinner" />{t('Loading view…')}</div>}>
            {view === 'overview' && <Overview data={data} qor={qor} skills={skills} kb={kb} telemetry={telemetry} busy={!!busy} onGo={go} onPick={pattern => { go('scoreboard'); pick(pattern) }} onRun={run} onReload={() => void loadAll()} />}
            {view === 'scoreboard' && (data ? <Scoreboard data={data} onPick={pick} /> : <div className="pane-empty" role="status"><Icon name="check-square" size={32} /><p>{busy ? t('Loading verification results…') : t('Verification results are unavailable.')}</p><button className="secondary-button" disabled={!!busy} onClick={() => void loadAll()}>{t('Retry')}</button></div>)}
            {view === 'waveform' && <WaveformPane />}
            {view === 'schematic' && <SchematicPane onSelect={(node: SchematicNode) => { setSel({ kind: 'flow', id: node.name || node.label, data: { label: node.label, type: node.type, class: node.cls, level: node.layer, width: `${node.width} bit`, source: node.src_line ? `rtl/gamma.v:${node.src_line}` : '', sequential: node.seq ? 'yes' : 'no' } }); setShowProps(true) }} />}
            {view === 'quality' && <Quality qor={qor} />}
            {view === 'signoff' && <SignoffView report={signoff} telemetry={telemetry} busy={busy === 'signoff'} error={signoffError} onRun={run} disabled={!!busy} />}
            {view === 'flows' && <Flows />}
            {view === 'improve' && <ImprovePane />}
            {view === 'knowledge' && <KnowledgePane />}
            {view === 'help' && <HelpPane />}
            {view === 'assistant' && <Assistant gatewayReady={gatewayReady} skills={skills} />}
          </Suspense></ErrorBoundary></div>
        </main>
        {showProps && <><Splitter axis="x" varName="--props-w" min={170} max={400} invert label="Properties width" /><Properties sel={sel} qor={qor} reference={isReference(data)} /></>}
      </div>
      {consoleOpen && <Splitter axis="y" varName="--console-h" min={80} max={480} invert label="Transcript height" />}
      <Console open={consoleOpen} onToggle={() => setConsoleOpen(!consoleOpen)} onExport={exportTranscript} />
      <footer className="statusbar"><span className="sb-item status-design"><span className="status-dot" />{data?.design.module ?? 'gamma'}<span className="muted"> / {data?.resultMode === 'snapshot' ? t('Saved snapshot') : health ? t('Backend connected') : t('Offline')}</span></span><span className="sb-spacer" /><button onClick={() => { resetPanes(shellRef.current); setShowNav(false); setShowProps(false); setConsoleOpen(false) }}>{t('Reset layout')}</button><span className="sb-item" role="status">{busy ? <><i className="spinner" />{busy === 'load' ? t('Refreshing…') : t('Running sign-off…')}</> : updatedAt ? `${t('updated')} ${updatedAt.toLocaleTimeString(lang === 'ko' ? 'ko-KR' : 'en-GB')}` : t('loading…')}</span></footer>
    </div>
    <CommandPalette open={searchOpen} onClose={() => setSearchOpen(false)} onGo={go} patterns={data?.patterns ?? []} onPick={pick} onReload={() => void loadAll()} busy={!!busy} />
  </div>
}
