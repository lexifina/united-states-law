// Builds the git history of the US Code (github.com/lexifina/united-states-law) from the same data and the same
// text-on-a-date logic as the reader at lexifina.com/watch/us-code.
//
// Each commit is one law taking effect: its author is the public law, and its date is the day the change came into
// force, not the day it was enacted or printed. `tools/uscode.py on <date> <file>` (shipped in the repository) reads the
// text on any date by the In-force trailers, and `git blame` names the law behind each provision. Changes the printed
// Code made that no law explains are committed on the day the version that printed them was current through, under
// the name of that version, so nothing is silently folded in.
//
// The data is read from app/watch/us-code/_data under the folder this runs in: the website's own folder for the titles
// the site shows, or a staging folder holding the whole Code (scripts/us-code-git-stage.mjs). Sections are worked out
// one at a time and their texts kept on disk, so the whole Code fits in memory.
//
// The build is deterministic: the same data gives the same commits and hashes. It refuses to write into a folder that
// is neither empty nor an earlier build of this history.
//   npx jiti scripts/us-code-git.ts <out>
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync, writeSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { attribute, textOn, type ReaderOrder } from '../app/watch/us-code/_components/onDate'
import {
  type ChangeRecord, type Edition, type SectionChange, type SectionFile,
  changeHref, coverageText, formatDate, inForceReason, KIND_LABEL, lawHref, lawLabel, meta, records,
  sectionChanges, sectionHref, sectionNumbers, STATUS_LABEL, titleHref, titleName, titles, where,
} from '../app/watch/us-code/_data/load'
import { CHANGES } from './us-code-git-changes'
import { LICENSE } from './us-code-git-license'
import { reproduce } from './us-code-git-reproduce'
import { USCODE_PY } from './us-code-git-tool'

// APPEND MODE (this file, us-code-git-append.ts): adds the titles staged under _data to an existing clone of the
// history as an end block, never rewriting it. The commits go on refs/heads/append, starting from the clone's HEAD: a
// starting commit with the staged titles' first printed text (Consolidated:), then one commit per law per in-force day,
// exactly as us-code-git.ts writes them. Their dates run from the first edition again, so they sit after later-dated
// commits; readers order by the In-force: trailer. Commit messages carry no reader links (the reader at
// lexifina.com/watch/us-code does not show these titles), and only law tags not already in the clone are added.
// Documentation is updated separately, as its own commit.
//   npx jiti scripts/us-code-git-append.ts <clone of lexifina/united-states-law>
if (!process.argv[2]) {
  console.error('usage: npx jiti scripts/us-code-git-append.ts <clone of the history>')
  process.exit(2)
}
const OUT = path.resolve(process.argv[2])
const NO_SITE = true
const SITE = 'https://lexifina.com'
const COMMITTER = { name: 'Lexifina', email: 'us-code-history@lexifina.com' }
const DATA_DIR = path.join(process.cwd(), 'app', 'watch', 'us-code', '_data')

// ---- One section, on any date ----

interface Sec {
  t: number
  n: string
  file: string                       // "title-11/1182.md"
  data: SectionFile
  order: ReaderOrder[]
  changes: SectionChange[]
  attributed: ReturnType<typeof attribute>
}

// Section files are read straight from disk, not through load.ts's cache, so only one is held at a time.
const readSection = (t: number, n: string): SectionFile => JSON.parse(readFileSync(path.join(DATA_DIR, `title${t}`, 'sections', `${n}.json`), 'utf8'))

// The heading on a date: the printed one, with any heading change not yet in force undone and any in force but not
// yet printed applied, as the reader does for the text.
function headingOn(s: Sec, date: string, base: string): string {
  const idx = (k: string) => s.order.findIndex((o) => o.key === k)
  const of = (k: string) => s.data.versions.find((v) => v.editions.includes(k))?.heading
  const live = (c: SectionChange) => c.inForce !== null && c.inForce <= date
  let heading = of(base) ?? s.data.heading
  for (const c of s.changes.filter((c) => c.heading)) {
    if (idx(c.to) <= idx(base) && !live(c)) heading = of(c.from) ?? heading
    else if (idx(c.to) > idx(base) && live(c)) heading = of(c.to) ?? heading
  }
  // A few sections are printed with no heading at all (an omitted or vacant section).
  return heading ?? ''
}

// Characters Markdown would read as formatting ("the symbol *M*") are escaped, so the file shows the Code's own text.
const escape = (s: string) => s.replace(/([\\*_`<])/g, '\\$1')

function render(s: Sec, date: string): string | null {
  const on = textOn(date, s.order, s.data.versions, s.attributed, s.changes, s.data.replays ?? [])
  if (on.before || !on.lines.length) return null
  const out = [`# ${s.t} U.S.C. § ${s.n}. ${escape(headingOn(s, date, on.base))}`, '']
  let listed = false
  for (const l of on.lines) {
    // Text rebuilt from a law's own words (a replay partway through a version) can carry the law's curly quotes; it is
    // normalised to the printed Code's form so a date in between does not read as a change.
    const text = escape(l.text.replace(/\s+/g, ' ').replace(/[“”]/g, '"').replace(/\.—\s+/g, '.—').trim())
    // Indentation follows the provision's designation ("(1)(B)(i)" is three deep), not the printed level: the editions
    // indent the same provision differently from year to year, which would make git blame credit a re-indent instead of
    // the law that wrote the words. Text outside any provision (a section with no subdivisions, its opening words, or an
    // undesignated paragraph) has no designation and stays a paragraph; closing text of a provision sits at its depth.
    const level = (/^((?:\([^()]+\))*)/.exec(l.path)?.[1].match(/\(/g) ?? []).length
    if (!text) continue
    if (level <= 0) {
      if (listed) out.push('')
      out.push(text, '')
      listed = false
    } else {
      out.push(`${'  '.repeat(level - 1)}- ${text}`)
      listed = true
    }
  }
  return `${out.join('\n').trimEnd()}\n`
}

// A section that is no longer in the Code keeps a file saying so, instead of disappearing.
const removed = (s: Sec, day: string, by: string) =>
  `# ${s.t} U.S.C. § ${s.n}. Repealed or transferred\n\nThis section is not in the Code on and after ${formatDate(day)}${by ? `, under ${by}` : ''}. Its earlier text is in the history: \`git log -p -- ${s.file}\`.\n`

// ---- Who a commit is by ----

interface Author { name: string; email: string }
const plain = (pl: string) => lawLabel(pl).replace('–', '-')
const lawAuthor = (pl: string, name: string): Author => ({ name: name && name !== plain(pl) ? `${plain(pl)} (${name})` : plain(pl), email: `pl-${pl}@public-law.invalid` })
const versionAuthor = (e: Edition): Author => ({
  name: e.kind === 'edition' ? `${e.year} edition of the US Code` : `US Code release point ${e.through_law}`,
  email: `${e.key}@uscode-version.invalid`,
})

// ---- Git ----

function git(args: string[], env: Record<string, string> = {}, input?: string): string {
  return execFileSync('git', args, { cwd: OUT, env: { ...process.env, ...env }, input, encoding: 'utf8', maxBuffer: 1 << 30 })
}

// Commits are written to a git fast-import stream on disk, then imported in one go: no working tree is scanned per
// commit, memory stays at one commit's files, and the result is the same objects and hashes as git commit would make.
const STREAM = path.join(os.tmpdir(), `us-code-git-${process.pid}.fi`)
let streamFd = -1
let mark = 0
let parent: string | null = null           // ":<mark>" or a commit hash
const pending = new Map<string, Buffer | null>()
const emit = (chunk: string | Buffer) => { writeSync(streamFd, typeof chunk === 'string' ? Buffer.from(chunk, 'utf8') : chunk) }
const blob = (b: Buffer) => { emit(`data ${b.length}\n`); emit(b); emit('\n') }

function commit(author: Author, date: string, message: string): string {
  // The replay marks a provision's closing words with "\u0000closing"; a summary quoting new text can carry it. Git
  // refuses NUL bytes in messages outside fast-import, so the marker never goes into a message.
  message = message.replace(/\u0000closing/g, '').replace(/\u0000/g, '')
  const when = `${Math.floor(Date.parse(`${date}T12:00:00Z`) / 1000)} +0000`
  mark++
  emit(`commit refs/heads/append\nmark :${mark}\nauthor ${author.name} <${author.email}> ${when}\ncommitter ${COMMITTER.name} <${COMMITTER.email}> ${when}\n`)
  blob(Buffer.from(message, 'utf8'))
  if (parent) emit(`from ${parent}\n`)
  for (const [rel, content] of Array.from(pending).sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
    if (content === null) emit(`D ${rel}\n`)
    else { emit(`M 100644 inline ${rel}\n`); blob(content) }
  }
  emit('\n')
  pending.clear()
  parent = `:${mark}`
  return parent
}

// Imports the stream written so far and returns each mark's commit hash.
function flush(): Map<string, string> {
  emit('done\n')
  closeSync(streamFd)
  const marks = path.join(os.tmpdir(), `us-code-git-${process.pid}.marks`)
  execFileSync('git', ['fast-import', '--quiet', '--done', `--export-marks=${marks}`], { cwd: OUT, stdio: [openSync(STREAM, 'r'), 'inherit', 'inherit'] })
  const map = new Map(readFileSync(marks, 'utf8').trim().split('\n').map((l) => l.split(' ') as [string, string]))
  rmSync(marks, { force: true })
  streamFd = openSync(STREAM, 'w')
  return map
}

function writeFile(rel: string, content: string | Buffer | null) {
  pending.set(rel, content === null ? null : typeof content === 'string' ? Buffer.from(content, 'utf8') : content)
}

const wrap = (s: string, width = 72, indent = '') => {
  const lines: string[] = []
  let line = ''
  for (const w of s.split(/\s+/).filter(Boolean)) {
    if (line && (line + ' ' + w).length > width) { lines.push(indent + line); line = w } else line = line ? `${line} ${w}` : w
  }
  if (line) lines.push(indent + line)
  return lines.join('\n')
}

// ---- The data ----

const MISSING_ONLY = process.argv.includes('--missing-sections')
const PRESENT = new Set(MISSING_ONLY ? git(['ls-tree', '-r', '--name-only', 'HEAD']).split('\n').map((l) => l.trim()).filter(Boolean) : [])

const recordById = new Map<string, ChangeRecord>()
const editions = new Map<string, Edition>()
const lawNames = new Map<string, string>()
const lawUrls = new Map<string, string>()
for (const t of titles()) {
  const m = meta(t)
  for (const e of m.editions) editions.set(e.key, e)
  for (const l of m.laws) { lawNames.set(l.pl, l.short_title || plain(l.pl)); lawUrls.set(l.pl, l.url) }
  for (const r of records(t)) recordById.set(r.id, r)
}

// The day the data was built. It dates the documentation commit and caps the history, so a rebuild on any later day
// gives the same commits.
const BUILT = titles().map((t) => meta(t).generated_at.slice(0, 10)).sort().pop() as string
// The first printed version is the starting text; everything after is a commit on the day it took effect.
const START = titles().map((t) => meta(t).editions[0].current_through).sort()[0]

// ---- Messages ----

// Who a change applies to, one trailer line per group of cases (groups are alternatives; a group's conditions all
// hold). No line means no scope note was found; what the change reaches is then a question of law (see corpus.json).
const CONDITION: Record<string, string> = {
  'on or after': 'commenced-on-or-after', before: 'commenced-before', after: 'commenced-after',
  'on or before': 'commenced-on-or-before', 'pending on': 'pending-on', 'before, on, or after': 'any-commencement',
}
type Group = { relation: string; date: string; source?: string; conditions?: { relation: string; date: string }[] }
function appliesLines(r: ChangeRecord): string[] {
  return ((r.applies?.to ?? []) as Group[]).map((g) => {
    const conds = (g.conditions?.length ? g.conditions : [{ relation: g.relation, date: g.date }])
      .map((c) => `${CONDITION[c.relation] ?? c.relation.replace(/\W+/g, '-')} ${c.date}`)
    // The provision that sets the scope, so a reader can check it was matched to the right amendment.
    const setBy = g.source ? ` | set-by ${g.source.replace(/–/g, '-')}` : ''
    return `Applies: ${r.title} U.S.C. ${where(r)} | ${conds.join('; ')}${setBy}`
  })
}

function changeLines(r: ChangeRecord): string[] {
  const out = [`${r.title} U.S.C. ${where(r)}. ${KIND_LABEL[r.kind]}. ${STATUS_LABEL[r.status]}.`]
  if (r.summary) out.push(wrap(r.summary, 72, '  '))
  if (r.instruction) out.push(wrap(`Instruction: ${r.instruction.label}.`, 72, '  '))
  for (const to of r.applies?.to ?? []) out.push(wrap(`Applies to ${to.text.charAt(0).toLowerCase()}${to.text.slice(1).replace(/\.$/, '')}.`, 72, '  '))
  if (!NO_SITE) out.push(`  ${SITE}${changeHref(r)}`)
  return out
}

function lawMessage(laws: string[], day: string, recs: ChangeRecord[]): string {
  const pl = laws[0]
  const mine = recs.filter((r) => r.law === pl)
  const name = lawNames.get(pl) ?? plain(pl)
  const places = Array.from(new Set(recs.map((r) => `${r.title} U.S.C. §${r.section}`)))
  const subject = `${name}: ${places.slice(0, 2).join(', ')}${places.length > 2 ? ` and ${places.length - 2} more` : ''}`
  const r0 = mine[0]
  const printed = editions.get(r0.edition_to)
  const head = [
    `${plain(pl)}, ${name}.`,
    `In force ${formatDate(day)}. ${inForceReason(r0)}`,
    `Enacted ${formatDate(r0.dates.enacted)}. First printed in ${printed ? (printed.kind === 'edition' ? `the ${printed.year} edition` : `release point ${printed.through_law}`) : r0.edition_to}.`,
  ].map((p) => wrap(p)).join('\n')
  const body = laws.map((l) => recs.filter((r) => r.law === l).map((r) => changeLines(r).join('\n')).join('\n\n')).join('\n\n')
  const trailers = [
    `Law: ${plain(pl)}`,
    `Enacted: ${r0.dates.enacted ?? 'unknown'}`,
    `In-force: ${day}`,
    `Printed-in: ${r0.edition_to}`,
    ...recs.flatMap(appliesLines),
    `Source: ${lawUrls.get(pl) ?? ''}`,
    ...(NO_SITE ? [] : [`Reader: ${SITE}${lawHref(pl)}`]),
    ...laws.slice(1).map((l) => `Co-authored-by: ${lawAuthor(l, lawNames.get(l) ?? l).name} <${lawAuthor(l, '').email}>`),
  ]
  return `${subject}\n\n${head}\n\n${body}\n\n${trailers.join('\n')}\n`
}

// ---- Phase 1: every section's versions, one section at a time ----

// Texts go into a content store on disk; events say which file changes to which text on which day, and why.
const STORE = path.join(os.tmpdir(), `us-code-git-${process.pid}`)
mkdirSync(STORE, { recursive: true })
const put = (text: string) => {
  const h = createHash('sha1').update(text).digest('hex')
  const f = path.join(STORE, h)
  if (!existsSync(f)) writeFileSync(f, text)
  return h
}
const take = (h: string) => readFileSync(path.join(STORE, h), 'utf8')

interface Event { day: string; file: string; text: string | null; key: string; recs: string[] }
const events: Event[] = []
const baseline = new Map<string, string>()   // file -> text hash on the first day
// Judicial Conference dollar adjustments (11 U.S.C. §104), by notice: they change the amount that applies without
// changing the printed words, so each becomes an empty commit on its effective date with Modifies: lines.
interface Modifies { where: string; effective: string; pairs: string; citation: string }
interface Notice { citation: string; effective: string; url: string; lines: Modifies[] }
const notices = new Map<string, Notice>()
const titleSections = new Map<number, number>()
for (const t of titles()) {
  const m = meta(t)
  const order = m.editions.map((e) => ({ key: e.key, label: e.label, through: e.current_through }))
  // With --missing-sections, a title already in the history gets only the sections it lacks (sections an earlier build
  // of the data left out).
  const numbers = sectionNumbers(t).filter((n) => !MISSING_ONLY || !PRESENT.has(`title-${t}/${n}.md`))
  titleSections.set(t, numbers.length)
  for (const n of numbers) {
    const data = readSection(t, n)
    const changes = sectionChanges(t, n)
    for (const a of data.adjustments) {
      if (a.effective <= START || a.effective > BUILT) continue
      const notice = notices.get(a.citation) ?? { citation: a.citation, effective: a.effective, url: a.url, lines: [] }
      for (const c of a.changes) {
        const [before, after] = c.text.split(' adjusted to ')
        const olds = Array.from((before ?? '').matchAll(/"([\d,]+)"/g)).map((m) => m[1])
        const news = Array.from((after ?? '').matchAll(/"([\d,]+)"/g)).map((m) => m[1])
        if (!olds.length || olds.length !== news.length) continue
        const pairs = olds.map((o, i) => `"$${o}" becomes "$${news[i]}"`).join('; ')
        notice.lines.push({ where: `title-${t}/${n}.md#${c.path || '(section)'}`, effective: a.effective, pairs, citation: a.citation })
      }
      if (notice.lines.length) notices.set(a.citation, notice)
    }
    const s: Sec = { t, n, file: `title-${t}/${n}.md`, data, order, changes, attributed: attribute(data.versions, changes) }
    // The text can only change on a day a change takes effect, or a day a printed version that differs, or that
    // prints one of this section's changes, becomes the latest.
    const versionOf = (k: string) => data.versions.findIndex((v) => v.editions.includes(k))
    const days = new Set<string>()
    for (const c of changes) if (c.inForce && c.inForce > START && c.inForce <= BUILT) days.add(c.inForce)
    order.forEach((o, i) => {
      if (i === 0 || o.through <= START || o.through > BUILT) return
      if (versionOf(o.key) !== versionOf(order[i - 1].key) || changes.some((c) => c.to === o.key)) days.add(o.through)
    })
    // `last` is the section's own text (null when it is not in the Code); the file shows a note while it is absent.
    let last = render(s, START)
    if (last !== null) baseline.set(s.file, put(last))
    let shown = last !== null
    const sorted = Array.from(days).sort()
    const texts = sorted.map((day) => render(s, day))
    for (let k = 0; k < sorted.length; k++) {
      const day = sorted[k]
      const next = texts[k]
      if (next === last) continue
      // A section missing from one printed version but back in a later one, with no law removing it that day, is a
      // gap in the publication, not a repeal: keep its text instead of recording a removal and a re-addition.
      const lawToday = changes.some((c) => c.inForce === day && c.law)
      if (next === null && last !== null && !lawToday && texts.slice(k + 1).some((t) => t !== null)) continue
      last = next
      const laws = Array.from(new Set(changes.filter((c) => c.inForce === day && c.law).map((c) => c.law as string))).sort()
      const key = laws.length ? `law:${laws.join('+')}` : `print:${order.find((o) => o.through === day)?.key ?? 'unknown'}`
      const recs = changes.filter((c) => c.inForce === day && c.law).map((c) => c.id)
      // A section that leaves the Code gets a note in its place; one that never existed before stays absent.
      const text = next ?? (shown ? removed(s, day, laws.map((l) => plain(l)).join(' and ')) : null)
      if (text === null) continue
      shown = true
      events.push({ day, file: s.file, text: put(text), key, recs })
    }
  }
}

// ---- Phase 2: the commits ----

// The clone must be this history, and must not already hold any of the staged titles.
function prepare() {
  if (!existsSync(path.join(OUT, '.git')) || !git(['log', '--format=%ce', 'HEAD']).split('\n').includes(COMMITTER.email)
      || git(['log', '-1', '--format=%cn', 'HEAD']).trim() !== COMMITTER.name) {
    console.error(`${OUT} is not a clone of this history; refusing.`)
    process.exit(2)
  }
  for (const t of titles()) {
    if (!MISSING_ONLY && git(['ls-tree', '--name-only', 'HEAD', `title-${t}`]).trim()) {
      console.error(`title ${t} is already in ${OUT}; refusing to add it twice.`)
      process.exit(2)
    }
  }
  try { git(['update-ref', '-d', 'refs/heads/append']) } catch { /* none yet */ }
  parent = git(['rev-parse', 'HEAD']).trim()
  streamFd = openSync(STREAM, 'w')
}
prepare()
const BASE = String(parent)
const existingTags = new Set(git(['tag', '-l']).split('\n').map((s) => s.trim()).filter(Boolean))

for (const [file, h] of Array.from(baseline).sort()) writeFile(file, take(h))
const first = editions.get('2017')
const timeline: [string, string][] = []   // [day, commit], in order
const named = titles().length === 1 ? `title ${titles()[0]}` : `titles ${titles().join(', ')}`
const addedFiles = Array.from(new Set([...Array.from(baseline.keys()), ...events.map((e) => e.file)])).sort()
const sectionsNamed = addedFiles.map((f) => f.replace(/^title-(\d+)\/(.+)\.md$/, '§$2')).join(', ')
timeline.push([START, commit(first ? versionAuthor(first) : COMMITTER, START, [
  MISSING_ONLY ? `The ${first?.year ?? 2017} edition of the US Code, ${named}: ${sectionsNamed}` : `The ${first?.year ?? 2017} edition of the US Code, ${named}`,
  '',
  wrap(MISSING_ONLY
    ? `Sections of ${named} that the earlier build of this history left out, because their numbers carry a capital letter (${sectionsNamed}), as in force on ${formatDate(START)}, the date the ${first?.year ?? 2017} edition is current through, as published by GovInfo. A section first enacted later is added by the commit for the law that made it. This commit and the ones after it start again from ${formatDate(START)}: order by the In-force: trailer, not by position in the log.`
    : `The text of ${named} in force on ${formatDate(START)}, the date the ${first?.year ?? 2017} edition is current through, as published by GovInfo. ${titles().length === 1 ? 'This title was' : 'These titles were'} added to the history after the others, so this commit and the ones after it, one for each law taking effect, start again from ${formatDate(START)}: order by the In-force: trailer, not by position in the log.`),
  '',
  // A snapshot, not a change: nothing came into force that day, so it has Consolidated: rather than In-force:.
  `Consolidated: ${START}`,
  `Printed-in: ${first?.key ?? '2017'}`,
  `Source: https://www.govinfo.gov/app/collection/uscode/${first?.year ?? 2017}`,
  '',
].join('\n'))])

const rank = (key: string) => (key.startsWith('law:') ? 0 : 1)
const byDay = new Map<string, Event[]>()
for (const e of events) byDay.set(e.day, [...(byDay.get(e.day) ?? []), e])
for (const n of Array.from(notices.values())) if (!byDay.has(n.effective)) byDay.set(n.effective, [])
const nextNotice = new Map<string, string[]>()   // provision -> its notices' effective dates, sorted
for (const n of Array.from(notices.values())) for (const m of n.lines) nextNotice.set(m.where, [...(nextNotice.get(m.where) ?? []), m.effective])
for (const [k, v] of Array.from(nextNotice)) nextNotice.set(k, Array.from(new Set(v)).sort())
function modifiesLine(m: Modifies): string {
  const later = (nextNotice.get(m.where) ?? []).find((d) => d > m.effective)
  const until = later ? new Date(Date.parse(`${later}T00:00:00Z`) - 86400000).toISOString().slice(0, 10) : ''
  return `Modifies: ${m.where} | amount-adjusted | ${m.effective}..${until} | ${m.pairs} | set-by ${m.citation}`
}
const NOTICE_AUTHOR: Author = { name: 'Judicial Conference of the United States', email: 'judicial-conference@federal-register.invalid' }
let lawCommits = 1
const lawTags: [string, string, string][] = []   // [law, day, commit] for the law/ tags
for (const day of Array.from(byDay.keys()).sort()) {
  const groups = new Map<string, Event[]>()
  for (const e of byDay.get(day) as Event[]) groups.set(e.key, [...(groups.get(e.key) ?? []), e])
  for (const key of Array.from(groups.keys()).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))) {
    const group = (groups.get(key) as Event[]).sort((a, b) => a.file.localeCompare(b.file))
    for (const e of group) writeFile(e.file, e.text === null ? null : take(e.text))
    const rest = key.slice(key.indexOf(':') + 1)
    let hash: string
    if (key.startsWith('law:')) {
      const laws = rest.split('+')
      const recs = group.flatMap((e) => e.recs).map((id) => recordById.get(id) as ChangeRecord)
      hash = commit(lawAuthor(laws[0], lawNames.get(laws[0]) ?? laws[0]), day, lawMessage(laws, day, recs))
      for (const pl of laws) lawTags.push([pl, day, hash])
    } else {
      const e = editions.get(rest)
      const places = group.map((g) => g.file.replace(/^title-(\d+)\/(.+)\.md$/, '$1 U.S.C. §$2'))
      hash = commit(e ? versionAuthor(e) : COMMITTER, day, [
        `Printed text differs: ${places.slice(0, 2).join(', ')}${places.length > 2 ? ` and ${places.length - 2} more` : ''}`,
        '',
        wrap(`The text below changed when ${e ? (e.kind === 'edition' ? `the ${e.year} edition` : `release point ${e.through_law}`) : 'a printed version'}, current through ${formatDate(day)}, became the latest printed version, and no law taking effect that day accounts for it. It is committed under that version's name, so the difference stays visible instead of being folded into a law's commit. Most are editorial changes by the publisher, or changes the record could not date, such as one that waits on an agency's determination.`),
        '',
        ...places.map((p) => `- ${p}`),
        '',
        `Printed-in: ${rest}`,
        `Source: ${e?.url ?? ''}`,
        '',
      ].join('\n'))
    }
    timeline.push([day, hash])
    lawCommits++
  }
  for (const n of Array.from(notices.values()).filter((x) => x.effective === day).sort((a, b) => a.citation.localeCompare(b.citation))) {
    const lines = Array.from(new Set(n.lines.map(modifiesLine))).sort()
    timeline.push([day, commit(NOTICE_AUTHOR, day, [
      `Dollar amounts adjusted by ${n.citation}: ${lines.length} provision${lines.length === 1 ? '' : 's'}`,
      '',
      wrap(`The Judicial Conference adjusts the dollar amounts in title 11 every three years under 11 U.S.C. §104, by a notice in the Federal Register. The Code keeps printing the amounts Congress enacted, so this commit changes no words. Each Modifies line gives the amount that applies from ${formatDate(day)} until the next notice.`),
      '',
      'Words-changed: no',
      `In-force: ${day}`,
      ...lines,
      `Source: ${n.url}`,
      '',
    ].join('\n'))])
    lawCommits++
  }
}
rmSync(STORE, { recursive: true, force: true })
const marks = flush()
const hashOf = (m: string) => marks.get(m) ?? m
parent = hashOf(String(parent))

// ---- No documentation commit here; only law tags that are not in the clone yet ----

let tagged = 0
const latest = new Map<string, string>()
for (const [pl, day, hash] of lawTags) {
  const name = `law/${pl}@${day}`
  if (!existingTags.has(name)) { emit(`reset refs/tags/${name}
from ${hashOf(hash)}

`); tagged++ }
  latest.set(pl, hash)
}
for (const [pl, hash] of Array.from(latest)) {
  if (!existingTags.has(`law/${pl}`)) { emit(`reset refs/tags/law/${pl}
from ${hashOf(hash)}

`); tagged++ }
}
flush()
closeSync(streamFd)
rmSync(STREAM, { force: true })
const head = git(['rev-parse', 'refs/heads/append']).trim()
const count = git(['rev-list', '--count', `${BASE}..${head}`]).trim()
writeFileSync(path.join(OUT, '.git', 'append-timeline.tsv'), timeline.map(([d, c]) => `${d}\t${hashOf(c)}`).join('\n') + '\n')
console.log(`${count} commits appended on refs/heads/append (${head}) after ${BASE}; ${tagged} new law tags; ${titleSections.get(titles()[0])} sections; timeline in .git/append-timeline.tsv`)
