import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { renderMD } from './md'

/**
 * Help — the user manual, rendered in the tool itself.
 *
 * A manual that only exists as a file in the repo is a manual nobody reads while
 * they are stuck. The heading list on the left is built from the document, so it
 * stays correct when the document changes.
 */

interface Heading { level: number; text: string; id: string }

function slug(t: string): string {
  return t.toLowerCase().replace(/[^a-z0-9가-힣]+/g, '-').replace(/^-|-$/g, '')
}

export function HelpPane() {
  const [doc, setDoc] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.doc('MANUAL')
      .then((d) => setDoc(d.text))
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
  }, [])

  const headings = useMemo<Heading[]>(() => {
    if (!doc) return []
    return doc.split('\n')
      .map((l) => /^(#{2,3})\s+(.*)$/.exec(l))
      .filter((m): m is RegExpExecArray => !!m)
      .map((m) => ({ level: m[1].length, text: m[2].trim(), id: slug(m[2].trim()) }))
  }, [doc])

  if (err) {
    return (
      <div className="pane-empty">
        <p>Manual unavailable.</p>
        <p className="muted small">{err} — it lives at <code>docs/MANUAL.md</code>.</p>
      </div>
    )
  }
  if (!doc) return <div className="pane-empty muted">Loading manual…</div>

  return (
    <div className="help">
      <nav className="help-toc">
        <div className="nav-title">Contents</div>
        {headings.map((h) => (
          <a key={h.id} href={`#${h.id}`}
             className={`help-toc-item help-toc-h${h.level}`}
             onClick={(e) => {
               e.preventDefault()
               document.getElementById(h.id)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
             }}>
            {h.text}
          </a>
        ))}
      </nav>
      <article className="help-body">
        {/* Heading anchors are injected around renderMD's output so the TOC can
            jump without teaching the markdown renderer about ids. */}
        {doc.split(/\n(?=#{2,3}\s)/).map((section, n) => {
          const m = /^(#{2,3})\s+(.*)$/.exec(section.split('\n')[0])
          return (
            <section key={n} id={m ? slug(m[2].trim()) : undefined} className="help-section">
              {renderMD(section)}
            </section>
          )
        })}
      </article>
    </div>
  )
}
