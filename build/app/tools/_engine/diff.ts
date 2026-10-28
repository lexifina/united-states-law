// Myers' O(ND) difference algorithm over arrays of keys, as used for paragraphs and for the words inside them.

export type Op = 'eq' | 'del' | 'ins'

export interface DiffOp {
  op: Op
  // Half-open ranges into a (for eq and del) and b (for eq and ins).
  aStart: number
  aEnd: number
  bStart: number
  bEnd: number
}

// Past this many edits the two sides are treated as wholly different, which keeps time and memory bounded on files
// that have little in common.
const MAX_EDITS = 2000

export function diff(a: string[], b: string[]): DiffOp[] {
  let start = 0
  while (start < a.length && start < b.length && a[start] === b[start]) start++
  let endA = a.length
  let endB = b.length
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA--
    endB--
  }
  const ops: DiffOp[] = []
  if (start > 0) ops.push({ op: 'eq', aStart: 0, aEnd: start, bStart: 0, bEnd: start })
  ops.push(...middle(a, b, start, endA, start, endB))
  if (endA < a.length) ops.push({ op: 'eq', aStart: endA, aEnd: a.length, bStart: endB, bEnd: b.length })
  return merge(ops)
}

function middle(a: string[], b: string[], a0: number, a1: number, b0: number, b1: number): DiffOp[] {
  const n = a1 - a0
  const m = b1 - b0
  if (n === 0 && m === 0) return []
  if (n === 0) return [{ op: 'ins', aStart: a0, aEnd: a0, bStart: b0, bEnd: b1 }]
  if (m === 0) return [{ op: 'del', aStart: a0, aEnd: a1, bStart: b0, bEnd: b0 }]
  const max = Math.min(n + m, MAX_EDITS)
  const offset = max + 1
  const v = new Int32Array(2 * max + 3)
  const trace: Int32Array[] = []
  let found = -1
  for (let d = 0; d <= max; d++) {
    // Keep only the part of the frontier this step can read back (diagonals -d-1 to d+1).
    trace.push(v.slice(offset - d - 1, offset + d + 2))
    for (let k = -d; k <= d; k += 2) {
      let x: number
      if (k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1])) x = v[offset + k + 1]
      else x = v[offset + k - 1] + 1
      let y = x - k
      while (x < n && y < m && a[a0 + x] === b[b0 + y]) {
        x++
        y++
      }
      v[offset + k] = x
      if (x >= n && y >= m) {
        found = d
        break
      }
    }
    if (found !== -1) break
  }
  if (found === -1) {
    return [
      { op: 'del', aStart: a0, aEnd: a1, bStart: b0, bEnd: b0 },
      { op: 'ins', aStart: a1, aEnd: a1, bStart: b0, bEnd: b1 },
    ]
  }
  // Walk back through the saved frontiers to recover the path.
  const steps: DiffOp[] = []
  let x = n
  let y = m
  for (let d = found; d > 0; d--) {
    const vd = trace[d]
    const at = (kk: number) => vd[kk + d + 1]
    const k = x - y
    const prevK = k === -d || (k !== d && at(k - 1) < at(k + 1)) ? k + 1 : k - 1
    const prevX = at(prevK)
    const prevY = prevX - prevK
    while (x > prevX && y > prevY) {
      steps.push({ op: 'eq', aStart: a0 + x - 1, aEnd: a0 + x, bStart: b0 + y - 1, bEnd: b0 + y })
      x--
      y--
    }
    if (x === prevX) steps.push({ op: 'ins', aStart: a0 + x, aEnd: a0 + x, bStart: b0 + y - 1, bEnd: b0 + y })
    else steps.push({ op: 'del', aStart: a0 + x - 1, aEnd: a0 + x, bStart: b0 + y, bEnd: b0 + y })
    x = prevX
    y = prevY
  }
  while (x > 0 && y > 0) {
    steps.push({ op: 'eq', aStart: a0 + x - 1, aEnd: a0 + x, bStart: b0 + y - 1, bEnd: b0 + y })
    x--
    y--
  }
  return steps.reverse()
}

// Join neighbouring operations of the same kind, and put each deletion before the insertion it sits beside.
export function merge(ops: DiffOp[]): DiffOp[] {
  const out: DiffOp[] = []
  for (const op of ops) {
    if (op.aStart === op.aEnd && op.bStart === op.bEnd) continue
    const last = out[out.length - 1]
    if (last && last.op === op.op) {
      last.aEnd = op.aEnd
      last.bEnd = op.bEnd
    } else {
      out.push({ ...op })
    }
  }
  // Within a run of changes with no equal part between them, group deletions first.
  const grouped: DiffOp[] = []
  let i = 0
  while (i < out.length) {
    if (out[i].op === 'eq') {
      grouped.push(out[i++])
      continue
    }
    let j = i
    while (j < out.length && out[j].op !== 'eq') j++
    const run = out.slice(i, j)
    const dels = run.filter((o) => o.op === 'del')
    const inss = run.filter((o) => o.op === 'ins')
    if (dels.length) grouped.push({ op: 'del', aStart: dels[0].aStart, aEnd: dels[dels.length - 1].aEnd, bStart: run[0].bStart, bEnd: run[0].bStart })
    if (inss.length) {
      const aAt = dels.length ? dels[dels.length - 1].aEnd : run[0].aStart
      grouped.push({ op: 'ins', aStart: aAt, aEnd: aAt, bStart: inss[0].bStart, bEnd: inss[inss.length - 1].bEnd })
    }
    i = j
  }
  return grouped
}
