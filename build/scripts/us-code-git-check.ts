// Checks the generated US Code git history (us-code-git.ts) against the record it was built from.
//   npx jiti scripts/us-code-git-check.ts [repo=../../us-code-history]
// A: every change, on the day before and the day it took effect. B: each tagged version against the printed text.
// C: the Markdown structure. D: commits, dates and coverage.
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { meta, records, section, sectionNumbers, titles, type ChangeRecord } from '../app/watch/us-code/_data/load'

const REPO = path.resolve(process.argv[2] ?? path.join(process.cwd(), '..', '..', 'us-code-history'))
const git = (...args: string[]) => execFileSync('git', args, { cwd: REPO, encoding: 'utf8', maxBuffer: 1 << 28, stdio: ['ignore', 'pipe', 'ignore'] })
const norm = (s: string) => s.toLowerCase().replace(/[–‑]/g, '-').replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/\.—\s+/g, '.—').replace(/\s+/g, ' ').trim()
const strip = (md: string) => md.split('\n').map((l) => l.replace(/^\s*- /, '')).filter((l) => l && !l.startsWith('# ')).map(norm)
const dayAfter = (d: string) => new Date(Date.parse(`${d}T00:00:00Z`) + 86400000).toISOString().slice(0, 10)
const at = new Map<string, string>()
const revOn = (d: string) => { if (!at.has(d)) at.set(d, git('rev-list', '-1', `--before=${dayAfter(d)}T00:00:00Z`, 'main').trim()); return at.get(d) as string }
const fileOn = (d: string, file: string): string | null => { const r = revOn(d); if (!r) return null; try { return git('show', `${r}:${file}`) } catch { return null } }

const out: Record<string, unknown> = {}
const recs: ChangeRecord[] = titles().flatMap((t) => records(t))

// ---- A: each change ----
const inForceOf = (r: ChangeRecord) => (r.applies ? r.applies.in_force.date : (r.dates.effective ?? r.dates.enacted))
const A = { checked: 0, ok: 0, afterMissing: [] as string[], beforeStillThere: [] as string[], skipped: {} as Record<string, number> }
const skip = (why: string) => { A.skipped[why] = (A.skipped[why] ?? 0) + 1 }
for (const r of recs) {
  const d = inForceOf(r)
  if (!r.law) { skip('no law'); continue }
  if (!d) { skip('no in-force date'); continue }
  if (r.part === 'heading') { skip('heading'); continue }
  if (d <= '2018-01-12') { skip('before first commit'); continue }
  // Several instructions can change the same provision on the same day; each record holds its own step, so only the
  // last one on a provision is checked against the day's text (and only the first against the day before).
  const near = (a: string, b: string) => a === '' || b === '' || a === b || a.startsWith(`${b}(`) || b.startsWith(`${a}(`)
  const same = recs.filter((s) => s !== r && s.title === r.title && s.section === r.section && s.part !== 'heading' && inForceOf(s) === d && near(s.path, r.path))
  const order = (x: ChangeRecord) => [x.edition_to, Number(x.id.split('-').pop())] as const
  const later = same.some((s) => order(s)[0] > order(r)[0] || (order(s)[0] === order(r)[0] && order(s)[1] > order(r)[1]))
  const earlier = same.some((s) => order(s)[0] < order(r)[0] || (order(s)[0] === order(r)[0] && order(s)[1] < order(r)[1]))
  if (later && earlier) { skip('middle step of a same-day chain'); continue }
  const file = `title-${r.title}/${r.section}.md`
  const now = fileOn(d, file)
  const prev = fileOn(new Date(Date.parse(`${d}T00:00:00Z`) - 86400000).toISOString().slice(0, 10), file)
  // The provision as the record has it after the change must be in the file on the day; the provision as it was
  // before must be gone (unless it reads the same), and must have been there the day before.
  const nowText = (now ? strip(now) : []).join(' ').replace(/—\s+/g, '—')
  const prevText = (prev ? strip(prev) : []).join(' ').replace(/—\s+/g, '—')
  const after = norm(r.after).replace(/—\s+/g, '—'), before = norm(r.before).replace(/—\s+/g, '—')
  A.checked++
  const missing = !later && after && !nowText.includes(after)
  const lingering = !later && before && before !== after && !after.includes(before) && nowText.includes(before)
  const notBefore = !earlier && before && !prevText.includes(before)
  if (missing) A.afterMissing.push(`${r.id} ${r.kind} ${r.status} in force ${d}: new text not in the file${prevText.includes(after) ? ' (already there the day before)' : ''}`)
  if (lingering) A.beforeStillThere.push(`${r.id} ${r.kind} in force ${d}: old text still in the file`)
  if (notBefore) (A as unknown as { oldNotBefore: string[] }).oldNotBefore = [...((A as unknown as { oldNotBefore?: string[] }).oldNotBefore ?? []), `${r.id} ${r.kind} in force ${d}`]
  if (!missing && !lingering) A.ok++
}
out.A = A

// ---- B: tags against the printed text ----
const B: Record<string, { sections: number; same: number; differ: string[] }> = {}
for (const t of titles()) {
  for (const e of meta(t).editions) {
    const tag = e.kind === 'edition' ? `edition-${e.year}` : `release-point-${e.through_law}`
    let rev = ''
    try { rev = git('rev-parse', tag).trim() } catch { continue }
    const row = (B[tag] ??= { sections: 0, same: 0, differ: [] })
    for (const n of sectionNumbers(t)) {
      const v = section(t, n).versions.find((x) => x.editions.includes(e.key))
      const printed = v && v.lines.length ? v.lines.map((l) => norm(l.text)).filter(Boolean) : null
      let mine: string[] | null = null
      try { mine = strip(git('show', `${rev}:title-${t}/${n}.md`)) } catch { mine = null }
      row.sections++
      if (JSON.stringify(printed) === JSON.stringify(mine)) row.same++
      else row.differ.push(`${t}/${n}`)
    }
  }
}
out.B = Object.fromEntries(Object.entries(B).map(([k, v]) => [k, { sections: v.sections, same: v.same, differ: v.differ.length, examples: v.differ.slice(0, 8) }]))

// ---- C: structure ----
const files = git('ls-files', 'title-*').trim().split('\n')
const C = { files: files.length, levelJumps: [] as string[], longest: [] as [number, string][], emptyBody: [] as string[], markdownRisk: [] as string[], flushAsItem: 0 }
for (const f of files) {
  const md = git('show', `HEAD:${f}`)
  const lines = md.split('\n')
  if (lines.filter((l) => l.trim() && !l.startsWith('# ')).length === 0) C.emptyBody.push(f)
  let prevLevel = 0
  for (const l of lines) {
    const m = l.match(/^(\s*)- (.*)$/)
    const level = m ? m[1].length / 2 + 1 : 0
    if (m && level > prevLevel + 1) C.levelJumps.push(`${f}: jump ${prevLevel}->${level} "${m[2].slice(0, 50)}"`)
    if (m && !/^\(/.test(m[2])) C.flushAsItem++
    if (/(^|\s)[*_`<>|]|^#|\[.*\]\(/.test(m ? m[2] : l) && !l.startsWith('# ')) C.markdownRisk.push(`${f}: ${l.trim().slice(0, 60)}`)
    if (l.trim()) prevLevel = level || (l.startsWith('# ') ? 0 : prevLevel)
    C.longest.push([l.length, f])
  }
}
C.longest = C.longest.sort((a, b) => b[0] - a[0]).slice(0, 5)
out.C = { ...C, levelJumps: { count: C.levelJumps.length, examples: C.levelJumps.slice(0, 6) }, markdownRisk: { count: C.markdownRisk.length, examples: C.markdownRisk.slice(0, 8) } }

// ---- D: commits ----
const log = git('log', '--reverse', '--format=%H%x09%aI%x09%cI%x09%an%x09%s').trim().split('\n').map((l) => l.split('\t'))
const body = git('log', '--format=%B%x00').split('\0')
const ids = new Set(Array.from(body.join('\n').matchAll(/\/changes\/([\w-]+)/g)).map((m) => m[1]))
const enactedAfter = recs.filter((r) => { const d = inForceOf(r); return d && r.dates.enacted && d < r.dates.enacted }).map((r) => `${r.id} in force ${inForceOf(r)} enacted ${r.dates.enacted}`)
let monotonic = true
for (let i = 1; i < log.length; i++) if (log[i][1] < log[i - 1][1]) monotonic = false
const notInMessages = recs.filter((r) => !ids.has(r.id)).map((r) => `${r.id} law=${r.law} ${r.part ?? ''} inForce=${inForceOf(r)} status=${r.status}`)
out.D = {
  commits: log.length, monotonicDates: monotonic, authorEqualsCommitter: log.every((l) => l[1] === l[2]),
  recordsTotal: recs.length, recordsNamedInCommits: ids.size, notInMessages: { count: notInMessages.length, list: notInMessages },
  inForceBeforeEnacted: enactedAfter,
  authors: Array.from(new Set(log.map((l) => l[3]))).length,
}
console.log(JSON.stringify(out, null, 1))
