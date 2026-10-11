import { useEffect, useRef, useState } from 'react'
import { Icon, type IconName } from './Icon'
import { NAVIGATION, type View } from '../navigation'
import { useT } from '../i18n'
import type { PatternResult } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  onGo: (view: View) => void
  patterns: PatternResult[]
  onPick: (pattern: PatternResult) => void
  onReload: () => void
  busy: boolean
}

export function CommandPalette({ open, onClose, onGo, patterns, onPick, onReload, busy }: Props) {
  const t = useT()
  const dialog = useRef<HTMLDialogElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const needle = query.trim().toLowerCase()
  const items: { id: string; title: string; detail: string; icon: IconName; run: () => void }[] = [
    ...NAVIGATION.map(item => ({ id: item.id, title: t(item.label), detail: t(item.description), icon: item.icon, run: () => onGo(item.id) })),
    ...patterns.map(pattern => ({ id: `pattern-${pattern.name}`, title: pattern.name, detail: t('Inspect test pattern'), icon: 'check-square' as const, run: () => { onGo('scoreboard'); onPick(pattern) } })),
    ...(!busy ? [{ id: 'reload', title: t('Reload all'), detail: t('Refresh verification results and project status.'), icon: 'refresh' as const, run: onReload }] : []),
  ].filter(item => `${item.title} ${item.detail} ${item.id}`.toLowerCase().includes(needle))

  useEffect(() => {
    if (open) { setQuery(''); setSelected(0); dialog.current?.showModal(); input.current?.focus() }
    else dialog.current?.close()
  }, [open])

  function choose(index: number) {
    const item = items[index]
    if (item) { onClose(); item.run() }
  }

  return <dialog ref={dialog} className="command-dialog" aria-label={t('Search workspace')} onCancel={onClose} onClose={onClose} onClick={event => {
    if (event.target === dialog.current) {
      const bounds = dialog.current.getBoundingClientRect()
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose()
    }
  }}>
    <div className="command-input-row">
      <Icon name="search" size={20} />
      <input ref={input} value={query} placeholder={t('Search pages, patterns, and actions…')} aria-label={t('Search workspace')}
        role="combobox" aria-controls="command-results" aria-expanded={open} aria-autocomplete="list"
        aria-activedescendant={items[selected] ? `command-${items[selected].id}` : undefined}
        onChange={event => { setQuery(event.target.value); setSelected(0) }}
        onKeyDown={event => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault()
            const next = Math.max(0, Math.min(items.length - 1, selected + (event.key === 'ArrowDown' ? 1 : -1)))
            setSelected(next)
            document.getElementById(`command-${items[next]?.id}`)?.scrollIntoView({ block: 'nearest' })
          }
          if (event.key === 'Enter') { event.preventDefault(); choose(selected) }
        }} />
      <button className="key-hint" onClick={onClose} aria-label={t('Close search')}>esc</button>
    </div>
    <div className="command-results" id="command-results" role="listbox" aria-label={t('Search results')}>
      {items.length ? items.map((item, index) => <div key={item.id} id={`command-${item.id}`} role="option" aria-selected={index === selected}
        className={`command-option ${index === selected ? 'command-selected' : ''}`} onMouseMove={() => setSelected(index)} onClick={() => choose(index)}>
        <Icon name={item.icon} /><span><strong>{item.title}</strong><small>{item.detail}</small></span><Icon name="arrow" size={16} />
      </div>) : <div className="command-empty">{t('No matches. Try a page name or test pattern.')}</div>}
    </div>
    <div className="command-footer"><span><kbd>↑</kbd><kbd>↓</kbd> {t('navigate')}</span><span><kbd>↵</kbd> {t('open')}</span><span><kbd>esc</kbd> {t('close')}</span></div>
  </dialog>
}
