// Mirror of backend app/limits.py measure_content:
// chars counted after trim; reads estimated as ceil(non-empty lines / 4).
export function measureContent(text) {
  const stripped = (text || '').trim()
  if (!stripped) return { char_count: 0, read_estimate: 0 }
  const normalized = stripped.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const nonempty = normalized.split('\n').filter((l) => l.trim()).length
  return { char_count: stripped.length, read_estimate: Math.ceil(nonempty / 4) }
}

export function limitViolation(size, limits) {
  if (!limits) return null
  if (size.char_count > limits.max_chars) {
    return `内容字符数 ${size.char_count} 超过上限 ${limits.max_chars}`
  }
  if (size.read_estimate > limits.max_reads) {
    return `粗估读段数 ${size.read_estimate} 超过上限 ${limits.max_reads}`
  }
  return null
}
