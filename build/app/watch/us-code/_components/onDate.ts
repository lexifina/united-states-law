// The text of a section on any date, and which change wrote each word, from the printed versions and the date each
// change took effect. Shared by the section reader in the browser and by the script that builds the public git
// history (scripts/us-code-git.ts), so both give the same text for the same date.
import { diff } from '../../../tools/_engine/diff'
import type { SectionChange, SectionLine, SectionReplay } from '../_data/load'

export interface ReaderVersion { editions: string[]; lines: SectionLine[] }
export interface ReaderOrder { key: string; label: string; through: string }
export type Tok = { s: string; c: string | null }
export type ALine = SectionLine & { toks: Tok[] }

export const tokens = (s: string) => s.match(/\s+|[\w$§%]+|[^\w\s]/g) ?? []
export const inTree = (line: string, path: string) => path === '' || line === path || (line.startsWith(path) && line[path.length] === '(')

// Each version's lines with the change that wrote each word, carried forward from version to version.
export function attribute(versions: ReaderVersion[], changes: SectionChange[]): ALine[][] {
  const out: ALine[][] = []
  versions.forEach((v, i) => {
    if (i === 0) {
      out.push(v.lines.map((l) => ({ ...l, toks: tokens(l.text).map((s) => ({ s, c: null })) })))
      return
    }
    const here = changes.filter((c) => !c.heading && v.editions.includes(c.to))
    const pick = (path: string, text: string): string | null => {
      const t = text.trim()
      const covering = here.filter((c) => inTree(path, c.path)).sort((a, b) => b.path.length - a.path.length)
      const pool = covering.length ? covering : here
      return (t && pool.find((c) => c.added.some((a) => a.includes(t) || (a.length > 3 && t.includes(a))))?.id) ?? pool[0]?.id ?? null
    }
    const seen = new Map<string, number>()
    const keyOf = (l: SectionLine) => {
      const n = seen.get(l.path) ?? 0
      seen.set(l.path, n + 1)
      return `${l.path}#${n}`
    }
    const prev = new Map(out[i - 1].map((l) => [keyOf(l), l]))
    seen.clear()
    // A provision renumbered or moved keeps its words' authors: an unmatched line is paired with the old line that
    // shares most of its words, when that is at least half of them.
    const keys = v.lines.map(keyOf)
    const used = new Set(keys.filter((k) => prev.has(k)))
    const wordsOf = (s: string) => new Set(s.toLowerCase().match(/[\w$§%]+/g) ?? [])
    const moved = new Map<number, ALine>()
    const prevWords = new Map(Array.from(prev).map(([k, o]) => [k, wordsOf(o.text)]))
    v.lines.forEach((l, j) => {
      if (prev.has(keys[j])) return
      const mine = wordsOf(l.text)
      let best: ALine | undefined
      let score = 0.5
      for (const [k, o] of Array.from(prev)) {
        if (used.has(k)) continue
        const theirs = prevWords.get(k) as Set<string>
        let common = 0
        mine.forEach((w) => { if (theirs.has(w)) common++ })
        const s = common / Math.max(mine.size, theirs.size, 1)
        if (s > score) { score = s; best = o }
      }
      if (best) {
        moved.set(j, best)
        used.add(Array.from(prev).find(([, o]) => o === best)![0])
      }
    })
    out.push(v.lines.map((l, j) => {
      const old = prev.get(keys[j]) ?? moved.get(j)
      if (old && old.text === l.text) return { ...l, toks: old.toks }
      const nt = tokens(l.text)
      if (!old) {
        const c = pick(l.path, l.text)
        return { ...l, toks: nt.map((s) => ({ s, c })) }
      }
      const ot = old.toks
      const toks: Tok[] = []
      for (const o of diff(ot.map((x) => x.s), nt)) {
        if (o.op === 'eq') for (let k = 0; k < o.aEnd - o.aStart; k++) toks.push({ s: nt[o.bStart + k], c: ot[o.aStart + k].c })
        else if (o.op === 'ins') {
          const run = nt.slice(o.bStart, o.bEnd)
          const c = pick(l.path, run.join(''))
          run.forEach((s) => toks.push({ s, c }))
        }
      }
      return { ...l, toks }
    }))
  })
  return out
}

// Replace the provision at `path` (and everything inside it) with the same provision from another text.
export function graft(lines: ALine[], path: string, from: ALine[]): ALine[] {
  if (path === '') return from
  const sub = from.filter((l) => inTree(l.path, path))
  const first = lines.findIndex((l) => inTree(l.path, path))
  const rest = lines.filter((l) => !inTree(l.path, path))
  if (first >= 0) {
    const at = lines.slice(0, first).filter((l) => !inTree(l.path, path)).length
    return [...rest.slice(0, at), ...sub, ...rest.slice(at)]
  }
  if (!sub.length) return lines
  const before = from[from.indexOf(sub[0]) - 1]
  const anchor = before ? rest.map((l) => l.path).lastIndexOf(before.path) : -1
  return [...rest.slice(0, anchor + 1), ...sub, ...rest.slice(anchor + 1)]
}

export interface OnDate { lines: ALine[]; base: string; before: boolean; notYet: SectionChange[]; early: SectionChange[] }

export function textOn(date: string, order: ReaderOrder[], versions: ReaderVersion[], attributed: ALine[][], changes: SectionChange[], replays: SectionReplay[]): OnDate {
  const idx = (k: string) => order.findIndex((o) => o.key === k)
  const vOf = (k: string) => attributed[Math.max(0, versions.findIndex((v) => v.editions.includes(k)))]
  const printed = order.filter((o) => o.through <= date)
  const base = (printed[printed.length - 1] ?? order[0]).key
  const b = idx(base)
  const byId = new Map(changes.map((c) => [c.id, c]))
  const live = (c: SectionChange) => c.inForce !== null && c.inForce <= date
  // One version can print several changes, some in force on the date and some not (a temporary change and the law
  // that later extended it). Its text on the date is the replay of those instructions up to the first not yet in force.
  const partial = new Map<SectionReplay, ALine[] | null>()
  const midway = (c: SectionChange): ALine[] | null => {
    const rp = replays.find((r) => r.steps.some((st) => st.record === c.id))
    if (!rp) return null
    if (partial.has(rp)) return partial.get(rp) ?? null
    const steps = rp.steps.filter((st) => byId.has(st.record))
    const upto = steps.findIndex((st) => !live(byId.get(st.record) as SectionChange))
    let result: ALine[] | null = null
    if (upto > 0) {
      let text: SectionLine[] = rp.start
      for (const st of rp.steps.slice(0, rp.steps.indexOf(steps[upto]))) {
        const next = [...text]
        for (const [start, end, added] of [...st.edits].reverse()) next.splice(start, end - start, ...added)
        text = next
      }
      // Words keep the author they have in either printed text; anything else is the last change applied.
      const known = [...vOf(rp.to), ...vOf(rp.from)]
      const last = steps[upto - 1].record
      result = text.map((l) => known.find((k) => k.path === l.path && k.text === l.text) ?? { ...l, toks: tokens(l.text).map((s) => ({ s, c: last })) })
    }
    partial.set(rp, result)
    return result
  }
  let lines = vOf(base)
  // Printed by then but not yet in force: the provision as it read before the change.
  const notYet = changes.filter((c) => !c.heading && idx(c.to) <= b && !live(c)).sort((x, y) => idx(y.to) - idx(x.to))
  for (const c of notYet) lines = graft(lines, c.path, midway(c) ?? vOf(c.from))
  // In force by then but printed only in a later version.
  const early = changes.filter((c) => !c.heading && idx(c.to) > b && live(c)).sort((x, y) => idx(x.to) - idx(y.to))
  for (const c of early) lines = graft(lines, c.path, midway(c) ?? vOf(c.to))
  return { lines, base, before: printed.length === 0, notYet, early }
}
