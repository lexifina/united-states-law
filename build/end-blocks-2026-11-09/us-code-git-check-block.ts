// Checks the generated US Code git history (us-code-git.ts) against the record it was built from. Run from the same
// folder as the build (the site, or the stage), so it reads the same data:
//   npx jiti scripts/us-code-git-check.ts <repo>
// A: every change, on the day it took effect and the day before. B: each tag against the printed text.
// C: the Markdown structure. D: commits, dates and coverage. Reads go through one `git cat-file --batch` per pass, so
// the whole Code checks in minutes.
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { meta, records, sectionNumbers, titles, type ChangeRecord, type SectionFile } from '../app/watch/us-code/_data/load'

const REPO = path.resolve(process.argv[2] ?? '')
if (!process.argv[2]) { console.error('usage: npx jiti scripts/us-code-git-check.ts <repo>'); process.exit(2) }
const DATA_DIR = path.join(process.cwd(), 'app', 'watch', 'us-code', '_data')
const git = (...args: string[]) => execFileSync('git', args, { cwd: REPO, encoding: 'utf8', maxBuffer: 1 << 30, stdio: ['ignore', 'pipe', 'ignore'] })

// Many "rev:path" reads in one process; a missing file reads as null.
function readMany(specs: string[]): (string | null)[] {
  if (!specs.length) return []
  const out = execFileSync('git', ['cat-file', '--batch'], { cwd: REPO, input: specs.join('\n') + '\n', maxBuffer: 0x7fffffff })
  const res: (string | null)[] = []
  let at = 0
  for (let i = 0; i < specs.length; i++) {
    const nl = out.indexOf(10, at)
    const head = out.subarray(at, nl).toString('utf8')
    if (head.endsWith(' missing') || head.endsWith(' ambiguous')) { res.push(null); at = nl + 1; continue }
    const size = Number(head.split(' ')[2])
    res.push(out.subarray(nl + 1, nl + 1 + size).toString('utf8'))
    at = nl + 1 + size + 1
  }
  return res
}

const norm = (s: string) => s.toLowerCase().replace(/[–‑]/g, '-').replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/\\([\\*_`<])/g, '$1').replace(/—\s+/g, '—').replace(/\s+/g, ' ').trim()
const strip = (md: string) => md.split('\n').map((l) => l.replace(/^\s*- /, '')).filter((l) => l && !l.startsWith('# ')).map(norm)
const dayBefore = (d: string) => new Date(Date.parse(`${d}T00:00:00Z`) - 86400000).toISOString().slice(0, 10)

// The commit in force on a date, by In-force trailer (as tools/uscode.py does).
// Block variant: RANGE=<base>..<tip> reads only an end block's commits (the title it adds is absent before it).
const RANGE = process.env.RANGE ?? 'HEAD'
const TIP = RANGE.includes('..') ? RANGE.split('..')[1] : RANGE
const hist = git('log', RANGE, '--reverse', '--date=short', '--format=%H%x1f%ad%x1f%(trailers:key=In-force,valueonly,separator=%x2c)%x1e')
  .split('\x1e').map((r) => r.trim()).filter(Boolean).map((r) => { const [h, ad, inf] = r.split('\x1f'); return [inf.trim().split(',')[0] || ad, h] as [string, string] })
const revOn = (d: string) => hist.filter(([day]) => day <= d).pop()?.[1] ?? null

const out: Record<string, unknown> = {}
const recs: ChangeRecord[] = titles().flatMap((t) => records(t))
const inForceOf = (r: ChangeRecord) => (r.applies ? r.applies.in_force.date : (r.dates.effective ?? r.dates.enacted))
const START = hist[0][0]

// ---- A: each change ----
const A = { checked: 0, ok: 0, afterMissing: [] as string[], beforeStillThere: [] as string[], oldNotBefore: [] as string[], skipped: {} as Record<string, number> }
const skip = (why: string) => { A.skipped[why] = (A.skipped[why] ?? 0) + 1 }
const near = (a: string, b: string) => a === '' || b === '' || a === b || a.startsWith(`${b}(`) || b.startsWith(`${a}(`)
const order = (x: ChangeRecord) => [x.edition_to, Number(x.id.split('-').pop())] as const
const bySecDay = new Map<string, ChangeRecord[]>()
for (const r of recs) { const k = `${r.title}/${r.section}/${inForceOf(r)}`; bySecDay.set(k, [...(bySecDay.get(k) ?? []), r]) }
const todo: { r: ChangeRecord; d: string; later: boolean; earlier: boolean }[] = []
for (const r of recs) {
  const d = inForceOf(r)
  if (!r.law) { skip('no law'); continue }
  if (!d) { skip('no in-force date'); continue }
  if (r.part === 'heading') { skip('heading'); continue }
  if (d <= START) { skip('before first commit'); continue }
  const same = (bySecDay.get(`${r.title}/${r.section}/${d}`) ?? []).filter((s) => s !== r && s.part !== 'heading' && near(s.path, r.path))
  const later = same.some((s) => order(s)[0] > order(r)[0] || (order(s)[0] === order(r)[0] && order(s)[1] > order(r)[1]))
  const earlier = same.some((s) => order(s)[0] < order(r)[0] || (order(s)[0] === order(r)[0] && order(s)[1] < order(r)[1]))
  if (later && earlier) { skip('middle step of a same-day chain'); continue }
  todo.push({ r, d, later, earlier })
}
const texts = readMany(todo.flatMap(({ r, d }) => [`${revOn(d)}:title-${r.title}/${r.section}.md`, `${revOn(dayBefore(d)) ?? hist[0][1]}:title-${r.title}/${r.section}.md`]))
todo.forEach(({ r, d, later, earlier }, i) => {
  const now = texts[2 * i], prev = texts[2 * i + 1]
  const nowText = (now ? strip(now) : []).join(' ').replace(/—\s+/g, '—')
  const prevText = (prev ? strip(prev) : []).join(' ').replace(/—\s+/g, '—')
  const after = norm(r.after).replace(/—\s+/g, '—'), before = norm(r.before).replace(/—\s+/g, '—')
  A.checked++
  const missing = !later && after && !nowText.includes(after)
  const lingering = !later && before && before !== after && !after.includes(before) && nowText.includes(before)
  const notBefore = !earlier && before && !prevText.includes(before)
  if (missing) A.afterMissing.push(`${r.id} ${r.kind} ${r.status} in force ${d}${prevText.includes(after) ? ' (already there the day before)' : ''}`)
  if (lingering) A.beforeStillThere.push(`${r.id} ${r.kind} in force ${d}`)
  if (notBefore) A.oldNotBefore.push(`${r.id} ${r.kind} in force ${d}`)
  if (!missing && !lingering) A.ok++
})
const tally = (xs: string[]) => xs.reduce((m, x) => { const k = x.split(' ').slice(1, -3).join(' ').replace(/ \(already.*/, ''); m[k] = (m[k] ?? 0) + 1; return m }, {} as Record<string, number>)
out.A = { ...A, afterMissing: { count: A.afterMissing.length, byKindStatus: tally(A.afterMissing.map((x) => x.replace(/ \(already there the day before\)$/, ''))), alreadyThere: A.afterMissing.filter((x) => x.endsWith('day before)')).length, list: A.afterMissing.filter((x) => !x.includes('partly')).concat(A.afterMissing.filter((x) => x.includes('partly'))).slice(0, 80) }, beforeStillThere: { count: A.beforeStillThere.length, list: A.beforeStillThere.slice(0, 40) }, oldNotBefore: { count: A.oldNotBefore.length, list: A.oldNotBefore.slice(0, 40) } }

// ---- B: tags against the printed text ----
// Every printed version has a tag on the last commit up to its date, so versions that changed nothing, and so have no
// commit of their own, are checked too. Headings are compared as well as the text.
const B: Record<string, { sections: number; same: number; differ: string[]; headings: string[] }> = {}
for (const t of (process.env.RANGE ? [] : titles())) {
  const numbers = sectionNumbers(t)
  const files = numbers.map((n) => JSON.parse(readFileSync(path.join(DATA_DIR, `title${t}`, 'sections', `${n}.json`), 'utf8')) as SectionFile)
  for (const e of meta(t).editions) {
    const tag = e.kind === 'edition' ? `edition-${e.year}` : `release-point-${e.through_law}`
    let rev = ''
    try { rev = git('rev-parse', tag).trim() } catch { continue }
    const mine = readMany(numbers.map((n) => `${rev}:title-${t}/${n}.md`))
    const row = (B[tag] ??= { sections: 0, same: 0, differ: [], headings: [] })
    numbers.forEach((n, i) => {
      const v = files[i].versions.find((x) => x.editions.includes(e.key))
      const printed = v && v.lines.length ? v.lines.map((l) => norm(l.text)).filter(Boolean) : null
      const m = mine[i] && !/^# .*Repealed or transferred/.test(mine[i] as string) ? strip(mine[i] as string) : null
      row.sections++
      if (JSON.stringify(printed) === JSON.stringify(m)) row.same++
      else row.differ.push(`${t}/${n}`)
      const head = m && v?.heading ? norm((mine[i] as string).split('\n')[0].replace(/^# .*?§ \S+\. /, '')) : null
      if (head !== null && head !== norm(v?.heading ?? '')) row.headings.push(`${t}/${n}`)
    })
  }
}
out.B = Object.fromEntries(Object.entries(B).map(([k, v]) => [k, { sections: v.sections, same: v.same, differ: v.differ.length, examples: v.differ.slice(0, 8), headingsDiffer: v.headings.length, headingExamples: v.headings.slice(0, 5) }]))

// ---- C: structure ----
const files = git('ls-tree', '-r', '--name-only', TIP).split('\n').filter((f) => /^title-\d+\//.test(f))
const C = { files: files.length, levelJumps: 0, codeBlockRisk: [] as string[], longest: [] as [number, string][], emptyBody: [] as string[] }
readMany(files.map((f) => `${TIP}:${f}`)).forEach((md, k) => {
  const f = files[k]
  const lines = (md ?? '').split('\n')
  if (lines.filter((l) => l.trim() && !l.startsWith('# ')).length === 0) C.emptyBody.push(f)
  let prevLevel = 0
  for (const l of lines) {
    const m = l.match(/^(\s*)- (.*)$/)
    const level = m ? m[1].length / 2 + 1 : 0
    if (m && level > prevLevel + 1) C.levelJumps++
    if (m && level >= 3 && prevLevel === 0) C.codeBlockRisk.push(`${f}: ${l.trim().slice(0, 50)}`)
    if (l.trim()) prevLevel = level || (l.startsWith('# ') ? 0 : prevLevel)
    C.longest.push([l.length, f])
  }
  C.longest = C.longest.sort((a, b) => b[0] - a[0]).slice(0, 3)
})
out.C = { ...C, codeBlockRisk: { count: C.codeBlockRisk.length, examples: C.codeBlockRisk.slice(0, 6) }, emptyBody: { count: C.emptyBody.length, examples: C.emptyBody.slice(0, 6) } }

// ---- D: commits ----
const log = git('log', RANGE, '--reverse', '--format=%H%x09%aI%x09%cI%x09%an').trim().split('\n').map((l) => l.split('\t'))
const ids = new Set(Array.from(git('log', RANGE, '--format=%B').matchAll(/\/changes\/([\w-]+)/g)).map((m) => m[1]))
let monotonic = true
for (let i = 1; i < log.length; i++) if (log[i][1] < log[i - 1][1]) monotonic = false
const notInMessages = recs.filter((r) => !ids.has(r.id))
out.D = {
  commits: log.length, monotonicDates: monotonic, authorEqualsCommitter: log.every((l) => l[1] === l[2]),
  recordsTotal: recs.length, recordsNamedInCommits: ids.size,
  notInMessages: { count: notInMessages.length, byReason: notInMessages.reduce((m, r) => { const k = !r.law ? 'no law' : !inForceOf(r) ? 'no in-force date' : (inForceOf(r) as string) <= START ? 'before first commit' : 'other'; m[k] = (m[k] ?? 0) + 1; return m }, {} as Record<string, number>), other: notInMessages.filter((r) => r.law && inForceOf(r) && (inForceOf(r) as string) > START).slice(0, 20).map((r) => r.id) },
  inForceBeforeEnacted: recs.filter((r) => { const d = inForceOf(r); return d && r.dates.enacted && d < r.dates.enacted }).length,
  authors: new Set(log.map((l) => l[3])).size,
}
console.log(JSON.stringify(out, null, 1))
