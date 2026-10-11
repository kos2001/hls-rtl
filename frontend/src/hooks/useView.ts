import { useCallback, useEffect, useState } from 'react'
import { isView, type View } from '../navigation'

function currentView(): View {
  const value = window.location.hash.slice(1)
  return isView(value) ? value : 'overview'
}

/** Bookmarkable views with browser back/forward support, without server routing. */
export function useView() {
  const [view, setView] = useState<View>(currentView)
  useEffect(() => {
    const sync = () => setView(currentView())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  const navigate = useCallback((next: View) => {
    setView(next)
    if (window.location.hash !== `#${next}`) window.location.hash = next
  }, [])
  return [view, navigate] as const
}
