import type { ReactNode } from 'react'

/** Minimal, dependency-free markdown renderer for agent output.
 *  Supports: ``` fenced code blocks, # / ## / ### headings, - / * lists,
 *  numbered lists, **bold**, `inline code`. Everything is built as React
 *  nodes (no innerHTML). Good enough for gateway chat/plan text. */

function inline(text: string, keyBase: string): ReactNode[] {
  // split on `code` and **bold**
  const out: ReactNode[] = []
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('`')) out.push(<code key={`${keyBase}-c${i++}`}>{tok.slice(1, -1)}</code>)
    else out.push(<strong key={`${keyBase}-b${i++}`}>{tok.slice(2, -2)}</strong>)
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function renderMD(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const lines = text.split('\n')
  let i = 0
  let key = 0
  while (i < lines.length) {
    const line = lines[i]

    // horizontal rule
    if (/^\s*(-{3,}|_{3,}|\*{3,})\s*$/.test(line)) {
      nodes.push(<div className="md-hr" key={`k${key++}`} />)
      i++
      continue
    }

    // fenced code block
    if (line.trimStart().startsWith('```')) {
      const buf: string[] = []
      i++
      while (i < lines.length && !lines[i].trimStart().startsWith('```')) {
        buf.push(lines[i])
        i++
      }
      i++ // closing fence
      nodes.push(<pre className="md-code" key={`k${key++}`}>{buf.join('\n')}</pre>)
      continue
    }

    // heading
    const h = /^(#{1,3})\s+(.*)$/.exec(line)
    if (h) {
      const cls = `md-h${h[1].length}`
      nodes.push(<div className={cls} key={`k${key++}`}>{inline(h[2], `k${key}`)}</div>)
      i++
      continue
    }

    // GFM table: a header row, a |---|---| separator, then body rows. The docs
    // lean on tables heavily (port lists, verdict meanings, troubleshooting), and
    // rendering them as raw pipes makes the manual unreadable.
    if (line.includes('|') && /^\s*\|?[\s:-]*-[\s:|-]*\|/.test(lines[i + 1] ?? '')) {
      const cells = (row: string) =>
        row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
      const head = cells(line)
      i += 2
      const body: string[][] = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
        body.push(cells(lines[i]))
        i++
      }
      nodes.push(
        <div className="md-table-wrap" key={`k${key++}`}>
          <table className="md-table">
            <thead>
              <tr>{head.map((h, n) => <th key={n}>{inline(h, `k${key}-h${n}`)}</th>)}</tr>
            </thead>
            <tbody>
              {body.map((row, rn) => (
                <tr key={rn}>
                  {row.map((c, cn) => <td key={cn}>{inline(c, `k${key}-${rn}-${cn}`)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    // blockquote
    if (/^\s*>\s?/.test(line)) {
      const buf: string[] = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      nodes.push(
        <div className="md-quote" key={`k${key++}`}>{renderMD(buf.join('\n'))}</div>,
      )
      continue
    }

    // list block (bulleted or numbered)
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const items: ReactNode[] = []
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        const item = lines[i].replace(/^\s*([-*]|\d+\.)\s+/, '')
        items.push(<li key={`k${key++}`}>{inline(item, `k${key}`)}</li>)
        i++
      }
      nodes.push(<ul className="md-list" key={`k${key++}`}>{items}</ul>)
      continue
    }

    // blank line -> spacing
    if (line.trim() === '') {
      nodes.push(<div className="md-gap" key={`k${key++}`} />)
      i++
      continue
    }

    // paragraph line (indented lines keep a mono look — spec-ish key: value)
    const mono = /^\s{2,}/.test(line) || /^[\w.]+\s*:\s+\S/.test(line)
    nodes.push(
      <div className={mono ? 'md-line md-mono' : 'md-line'} key={`k${key++}`}>
        {inline(line, `k${key}`)}
      </div>,
    )
    i++
  }
  return nodes
}
