export function downloadFile(name: string, content: string, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  // Keep the URL alive until the browser has started the download.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
