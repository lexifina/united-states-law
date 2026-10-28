// Builds the public git history of the US Code (github.com/lexifina/us-code-history) from the same data and the same
// text-on-a-date logic as the reader at lexifina.com/watch/us-code.
//
// Each commit is one law taking effect: its author is the public law, and its date
// is the day the change came into force, not the day it was enacted or printed. The text on any date is therefore
// `git show $(git rev-list -1 --before=<date> main):title-11/1182.md`, and `git blame` names the law behind each
// provision. Changes the printed Code made that no law explains are committed on the day the version that printed them
// was current through, under the name of that version, so nothing is silently folded in.
//
// The build is deterministic: the same data gives the same commits and hashes.
//   npx jiti scripts/us-code-git.ts [out=../../us-code-history]
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { attribute, textOn, type ReaderOrder } from '../app/watch/us-code/_components/onDate'
import {
  type ChangeRecord, type Edition, type SectionChange, type SectionFile,
  changeHref, coverageText, formatDate, inForceReason, KIND_LABEL, lawHref, lawLabel, meta, records, section,
  sectionChanges, sectionHref, sectionNumbers, STATUS_LABEL, titleHref, titleName, titles, where,
} from '../app/watch/us-code/_data/load'
import { LICENSE } from './us-code-git-license'
import { reproduce } from './us-code-git-reproduce'

const OUT = path.resolve(process.argv[2] ?? path.join(process.cwd(), '..', '..', 'us-code-history'))
const SITE = 'https://lexifina.com'
const COMMITTER = { name: 'Lexifina', email: 'us-code-history@lexifina.com' }

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

const inTree = (line: string, at: string) => at === '' || line === at || (line.startsWith(at) && line[at.length] === '(')

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
  return heading
}

function render(s: Sec, date: string): string | null {
  const on = textOn(date, s.order, s.data.versions, s.attributed, s.changes, s.data.replays ?? [])
  if (on.before || !on.lines.length) return null
  const lines = on.lines
  const out = [`# ${s.t} U.S.C. § ${s.n}. ${headingOn(s, date, on.base)}`, '']
  let listed = false
  for (const l of lines) {
    // Text rebuilt from a law's own words (a replay partway through a version) can carry the law's curly quotes; it is
    // normalised to the printed Code's form so a date in between does not read as a change.
    const text = l.text.replace(/\s+/g, ' ').replace(/[“”]/g, '"').replace(/\.—\s+/g, '.—').trim()
    // Levels in the record start at 0 for a section's top provisions; text outside any provision (a section with no
    // subdivisions, or its opening words) has no designation and stays a paragraph.
    const level = l.path === '' ? 0 : l.level + 1
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
  return execFileSync('git', args, { cwd: OUT, env: { ...process.env, ...env }, input, encoding: 'utf8', maxBuffer: 1 << 28 })
}

function commit(author: Author, date: string, message: string) {
  const when = `${date}T12:00:00Z`
  git(['add', '-A'])
  git(['commit', '-q', '--allow-empty-message', '-F', '-'], {
    GIT_AUTHOR_NAME: author.name, GIT_AUTHOR_EMAIL: author.email, GIT_AUTHOR_DATE: when,
    GIT_COMMITTER_NAME: COMMITTER.name, GIT_COMMITTER_EMAIL: COMMITTER.email, GIT_COMMITTER_DATE: when,
  }, message)
}

function writeFile(rel: string, content: string | null) {
  const full = path.join(OUT, rel)
  if (content === null) {
    if (existsSync(full)) rmSync(full)
    return
  }
  mkdirSync(path.dirname(full), { recursive: true })
  writeFileSync(full, content)
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

// ---- Load ----

const secs: Sec[] = []
const recordById = new Map<string, ChangeRecord>()
const editions = new Map<string, Edition>()
const lawNames = new Map<string, string>()
for (const t of titles()) {
  const m = meta(t)
  for (const e of m.editions) editions.set(e.key, e)
  for (const l of m.laws) lawNames.set(l.pl, l.short_title || lawLabel(l.pl).replace('–', '-'))
  for (const r of records(t)) recordById.set(r.id, r)
  const order = m.editions.map((e) => ({ key: e.key, label: e.label, through: e.current_through }))
  for (const n of sectionNumbers(t)) {
    const data = section(t, n)
    const changes = sectionChanges(t, n)
    secs.push({ t, n, file: `title-${t}/${n}.md`, data, order, changes, attributed: attribute(data.versions, changes) })
  }
}
const lawUrl = (pl: string) => Array.from(titles()).flatMap((t) => meta(t).laws).find((l) => l.pl === pl)?.url ?? ''

// The day the data was built. It dates the documentation commit and caps the history, so a rebuild on any later day
// gives the same commits.
const BUILT = titles().map((t) => meta(t).generated_at.slice(0, 10)).sort().pop() as string

// The first printed version is the starting text; everything after is a commit on the day it took effect.
const start = secs.reduce((d, s) => (s.order[0].through < d ? s.order[0].through : d), '9999')
const dates = new Set<string>()
for (const s of secs) {
  for (const c of s.changes) if (c.inForce && c.inForce > start && c.inForce <= BUILT) dates.add(c.inForce)
  for (const o of s.order) if (o.through > start && o.through <= BUILT) dates.add(o.through)
}
const days = Array.from(dates).sort()

// ---- Messages ----

function changeLines(r: ChangeRecord): string[] {
  const out = [`${r.title} U.S.C. ${where(r)}. ${KIND_LABEL[r.kind]}. ${STATUS_LABEL[r.status]}.`]
  if (r.summary) out.push(wrap(r.summary, 72, '  '))
  if (r.instruction) out.push(wrap(`Instruction: ${r.instruction.label}.`, 72, '  '))
  for (const to of r.applies?.to ?? []) out.push(wrap(`Applies to ${to.text.charAt(0).toLowerCase()}${to.text.slice(1).replace(/\.$/, '')}.`, 72, '  '))
  out.push(`  ${SITE}${changeHref(r)}`)
  return out
}

function lawMessage(pl: string, day: string, recs: ChangeRecord[], files: string[]): string {
  const name = lawNames.get(pl) ?? lawLabel(pl)
  const places = Array.from(new Set(recs.map((r) => `${r.title} U.S.C. §${r.section}`)))
  const subject = `${name}: ${places.slice(0, 2).join(', ')}${places.length > 2 ? ` and ${places.length - 2} more` : ''}`
  const r0 = recs[0]
  const printed = editions.get(r0.edition_to)
  const head = [
    `${lawLabel(pl).replace('–', '-')}, ${name}.`,
    `In force ${formatDate(day)}. ${inForceReason(r0)}`,
    `Enacted ${formatDate(r0.dates.enacted)}. First printed in ${printed ? (printed.kind === 'edition' ? `the ${printed.year} edition` : `release point ${printed.through_law}`) : r0.edition_to}.`,
  ].map((p) => wrap(p)).join('\n')
  const body = recs.map((r) => changeLines(r).join('\n')).join('\n\n')
  const trailers = [
    `Law: ${lawLabel(pl).replace('–', '-')}`,
    `Enacted: ${r0.dates.enacted ?? 'unknown'}`,
    `In-force: ${day}`,
    `Printed-in: ${r0.edition_to}`,
    `Source: ${lawUrl(pl)}`,
    `Reader: ${SITE}${lawHref(pl)}`,
  ]
  void files
  return `${subject}\n\n${head}\n\n${body}\n\n${trailers.join('\n')}\n`
}

// ---- Build ----

// The history is rebuilt from scratch, keeping only where it is published.
let remote = ''
try { remote = existsSync(path.join(OUT, '.git')) ? git(['remote', 'get-url', 'origin']).trim() : '' } catch { remote = '' }
if (existsSync(OUT)) for (const f of readdirSync(OUT)) rmSync(path.join(OUT, f), { recursive: true, force: true })
mkdirSync(OUT, { recursive: true })
git(['init', '-q', '-b', 'main'])
git(['config', 'core.autocrlf', 'false'])
if (remote) git(['remote', 'add', 'origin', remote])

let current = new Map<string, string | null>()
for (const s of secs) {
  const text = render(s, start)
  current.set(s.file, text)
  writeFile(s.file, text)
}
const first = editions.get('2017')
commit(first ? versionAuthor(first) : COMMITTER, start, [
  `The ${first?.year ?? 2017} edition of the US Code, titles ${titles().join(', ')}`,
  '',
  wrap(`The text in force on ${formatDate(start)}, the date the ${first?.year ?? 2017} edition is current through, as published by GovInfo. Every later commit is one law taking effect.`),
  '',
  `Source: ${first?.url ?? ''}`,
  '',
].join('\n'))

const tagAt = new Map<string, string>()     // edition key -> commit
let commits = 1
for (const day of days) {
  const next = new Map<string, string | null>()
  for (const s of secs) next.set(s.file, render(s, day))
  const changed = secs.filter((s) => next.get(s.file) !== current.get(s.file))
  // Group the files that changed today by what changed them: each law in force today, then whatever the newly printed
  // version changed that no law taking effect today explains.
  const groups = new Map<string, Sec[]>()
  for (const s of changed) {
    const laws = Array.from(new Set(s.changes.filter((c) => c.inForce === day && c.law).map((c) => c.law as string))).sort()
    const key = laws.length ? `law:${laws.join('+')}` : `print:${s.order.find((o) => o.through === day)?.key ?? 'unknown'}`
    groups.set(key, [...(groups.get(key) ?? []), s])
  }
  const keys = Array.from(groups.keys()).sort((a, b) => (a.split(':')[0] === b.split(':')[0] ? a.localeCompare(b) : ['law', 'print'].indexOf(a.split(':')[0]) - ['law', 'print'].indexOf(b.split(':')[0])))
  for (const key of keys) {
    const group = groups.get(key) as Sec[]
    for (const s of group) writeFile(s.file, next.get(s.file) ?? null)
    const [kind, rest] = [key.slice(0, key.indexOf(':')), key.slice(key.indexOf(':') + 1)]
    if (kind === 'law') {
      const laws = rest.split('+')
      const recs = group.flatMap((s) => s.changes.filter((c) => c.inForce === day && c.law && laws.includes(c.law)).map((c) => recordById.get(c.id) as ChangeRecord))
      const byLaw = laws.map((pl) => recs.filter((r) => r.law === pl))
      let message = lawMessage(laws[0], day, byLaw[0], group.map((s) => s.file))
      for (const [i, pl] of Array.from(laws.slice(1).entries())) {
        message = message.replace(/\n\nLaw: /, `\n\n${byLaw[i + 1].map((r) => changeLines(r).join('\n')).join('\n\n')}\n\nLaw: `)
        message += `Co-authored-by: ${lawAuthor(pl, lawNames.get(pl) ?? pl).name} <${lawAuthor(pl, '').email}>\n`
      }
      commit(lawAuthor(laws[0], lawNames.get(laws[0]) ?? laws[0]), day, message)
    } else {
      const e = editions.get(rest)
      const places = group.map((s) => `${s.t} U.S.C. §${s.n}`)
      commit(e ? versionAuthor(e) : COMMITTER, day, [
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
    commits++
  }
  current = next
  for (const [k, e] of Array.from(editions)) if (e.current_through === day) tagAt.set(k, git(['rev-parse', 'HEAD']).trim())
}

// ---- Documentation, the build itself and its data, added last ----

const lastLaw = git(['rev-parse', 'HEAD']).trim()
const totals = { records: recordById.size, replayed: Array.from(recordById.values()).filter((r) => r.status === 'replayed').length }
const titleRows = titles().map((t) => {
  const n = secs.filter((s) => s.t === t).length
  const c = records(t).length
  return `| [Title ${t}](title-${t}/) | ${titleName(t)} | ${n} | ${c} | [Read it](${SITE}${titleHref(t)}) |`
})

// The files this build runs on, copied byte for byte under build/ at the same paths, so the repository rebuilds itself:
// `cd build && npx jiti scripts/us-code-git.ts <empty folder>`.
const SITE_ROOT = process.cwd()
const CODE = [
  'scripts/us-code-git.ts', 'scripts/us-code-git-license.ts', 'scripts/us-code-git-reproduce.ts', 'scripts/us-code-git-check.ts',
  'app/watch/us-code/_data/load.ts', 'app/watch/us-code/_components/onDate.ts', 'app/watch/us-code/_components/words.ts',
  'app/tools/_engine/diff.ts',
]
const walk = (dir: string): string[] => readdirSync(path.join(SITE_ROOT, dir)).sort().flatMap((f) => {
  const rel = `${dir}/${f}`
  return statSync(path.join(SITE_ROOT, rel)).isDirectory() ? walk(rel) : [rel]
})
const DATA = walk('app/watch/us-code/_data').filter((f) => !f.endsWith('.ts'))
const sha256 = (b: Buffer | string) => createHash('sha256').update(b).digest('hex')
const sums: string[] = []
for (const rel of [...CODE, ...DATA]) {
  const bytes = readFileSync(path.join(SITE_ROOT, rel))
  mkdirSync(path.dirname(path.join(OUT, 'build', rel)), { recursive: true })
  writeFileSync(path.join(OUT, 'build', rel), bytes)
  if (DATA.includes(rel)) sums.push(`${sha256(bytes)}  ${rel}`)
}
const manifest = `${sums.join('\n')}\n`
writeFile('build/DATA-SHA256SUMS', manifest)
const blobs = CODE.map((rel) => ({ rel, blob: git(['hash-object', path.join(OUT, 'build', rel)]).trim() }))

// Where the data came from, read from the data itself.
const allEditions = titles().flatMap((t) => meta(t).editions)
const allLaws = new Map(titles().flatMap((t) => meta(t).laws).map((l) => [l.url, l]))
const notices = new Set(secs.flatMap((s) => s.data.adjustments).map((a) => a.url))
const span = (xs: string[]) => {
  const d = xs.filter(Boolean).map((x) => x.slice(0, 10)).sort()
  if (!d.length) return ''
  return d[0] === d[d.length - 1] ? formatDate(d[0]) : `${formatDate(d[0])} to ${formatDate(d[d.length - 1])}`
}
const recsAll = Array.from(recordById.values())
const lawsAll = titles().flatMap((t) => meta(t).laws)
const kind = (k: Edition['kind']) => allEditions.filter((e) => e.kind === k)
writeFile('README.md', readme(titleRows, totals, commits + 1))
writeFile('LICENSE.md', LICENSE)
writeFile('REPRODUCE.md', reproduce({
  built: BUILT, lastLaw, lawCommits: commits, sections: secs.length, titles: titles(),
  editions: { count: kind('edition').length, fetched: span(kind('edition').map((e) => e.fetched_at)) },
  releasePoints: { count: kind('release_point').length, fetched: span(kind('release_point').map((e) => e.fetched_at)) },
  laws: { count: allLaws.size, fetched: span(Array.from(allLaws.values()).map((l) => l.fetched_at)) },
  notices: notices.size,
  generated: span(titles().map((t) => meta(t).generated_at)),
  methodVersion: Array.from(new Set(titles().map((t) => meta(t).method_version))).join(', '),
  summaries: {
    changes: recsAll.length, changesByModel: recsAll.filter((r) => r.summary_source === 'model, checked').length,
    laws: lawsAll.length, lawsByModel: lawsAll.filter((l) => l.summary_source === 'model, checked').length,
  },
  dataSha256: sha256(manifest), dataFiles: DATA.length, blobs,
}))
commit({ name: COMMITTER.name, email: COMMITTER.email }, BUILT, [
  'Documentation, and the build with its data',
  '',
  wrap('README, LICENSE and REPRODUCE, and under build/ the script that made this history, the code it runs and the data it reads, byte for byte, so the history can be rebuilt and checked.'),
  '',
].join('\n'))

git(['tag', '-l']).split('\n').filter(Boolean).forEach((tag) => git(['tag', '-d', tag]))
const startCommit = git(['rev-list', '--max-parents=0', 'HEAD']).trim()
for (const e of Array.from(editions.values())) {
  const at = e.current_through === start ? startCommit : tagAt.get(e.key)
  if (at) git(['tag', e.kind === 'edition' ? `edition-${e.year}` : `release-point-${e.through_law}`, at])
}
console.log(`${commits + 1} commits, ${secs.length} sections, ${days.length} dates -> ${OUT}`)

function readme(rows: string[], t: { records: number; replayed: number }, n: number): string {
  const ex = 'title-11/1182.md'
  return `# Git for the US Code

The text of nine titles of the United States Code, with a commit for each law on each day its changes to them took effect, since the 2017 edition. **Each commit is a law taking effect.** Its author is the public law that made the change, and its date is the day the change came into force.

So the questions a lawyer asks of a statute become git commands:

| The question | The command |
| --- | --- |
| What did §1182 say on 1 May 2022? | \`git show $(git rev-list -1 --before=2022-05-01T23:59:59Z main):${ex}\` |
| Which law wrote each provision? | \`git blame ${ex}\` |
| What changed between two dates? | \`git diff $(git rev-list -1 --before=2019-12-31T23:59:59Z main) $(git rev-list -1 --before=2022-12-31T23:59:59Z main) -- ${ex}\` |
| Everything one law changed | \`git log -p --author="Pub. L. 116-136"\` |
| Every change to a section | \`git log -p -- ${ex}\` |
| The law in force on the day a printed version is current through | \`git checkout edition-2022\` or \`git checkout release-point-119-73\` |

Give the date with a time, as above. With a bare date git uses the current time of day, and every commit is stamped at noon UTC, so the answer for the day a law took effect would depend on when you ask. In PowerShell, put the revision in a variable first: \`$r = git rev-list -1 --before=2022-05-01T23:59:59Z main; git show "$($r):${ex}"\`.

A tag such as \`edition-2019\` is the law **in force** on the day that version is current through. It differs from the printed version wherever a change was printed before it took effect: the 2019 edition printed the Small Business Reorganization Act, which took effect in February 2020.

If you would rather not use a terminal, the same history has a reader at **[lexifina.com/watch/us-code](${SITE}/watch/us-code)**: pick a date and read the text in force on it, see the Act behind each phrase in colour, and see what else in the title relies on a provision. For example, [11 U.S.C. §1182](${SITE}${sectionHref(11, '1182')}).

## What is here

| Title | Name | Sections | Changes | Reader |
| --- | --- | ---: | ---: | --- |
${rows.join('\n')}

Each section is one Markdown file, \`title-<n>/<section>.md\`, with one provision per line, so \`git blame\` names a law for every paragraph, subparagraph and clause. The history covers ${coverageText()}. There are ${n} commits.

## Three dates, and the one we use

Every change has at least three dates: when the law was enacted, when the change took effect, and when it first appeared in a printed version of the Code. They are often far apart. An amendment can be printed months before it takes effect, and can take effect before the next version prints it.

Commits are dated when a change **took effect**, because that is the date that decides which text governs a set of facts. Each commit message carries the other two (\`Enacted:\` and \`Printed-in:\`) and says why the change took effect when it did: a date in the amending provision, an effective-date note, or, where neither says anything, the date of enactment, which is the default rule for federal statutes.

One section shows why this matters. The definition of a small business debtor in [11 U.S.C. §1182(1)](${SITE}${sectionHref(11, '1182')}) has had five different texts since 2019. A temporary $7.5 million debt limit lapsed in March 2022 and a new Act restored it in June 2022, reaching back to cases filed in between. \`git log -p -- ${ex}\` shows each step on the day it took effect.

## How the history is checked

Comparing two printed versions shows *what* changed but not *why*. So for each pair of versions we took the public laws enacted in between, carried out their amending instructions ("by striking … and inserting …") on the older text in date order, and compared the result with the newer version. Of ${t.records} changes, ${t.replayed} reproduced the next printed version exactly. Every commit says how its change was confirmed:

- **Confirmed by replay.** Carrying out the law's instructions gives the printed text word for word.
- **Partly confirmed**, or **publisher's note only.** The law was found but its instructions could not all be carried out, so the change rests partly or wholly on the publisher's amendment note.

One kind of commit is not a law:

- **Printed text differs.** Where a newly printed version reads differently and no law taking effect that day accounts for it, the difference is committed under that version's name on the day it is current through. Most are editorial; a few are changes the record could not date. They are kept visible instead of being folded into a law's commit.

## What "author" means here

The author of a line is the **enacted law** that wrote it, not the legislator who drafted or proposed it. This history covers the Code as enacted. It does not cover bills, amendments that failed, or who voted for what.

## What it does not show

- **Court decisions.** A provision a court has held unconstitutional stays in the text, because courts do not change the text of the Code.
- **A law reaching back.** When a law applies to cases from before it was enacted, the commit message says so (\`Applies to …\`), but the text on the earlier dates is not rewritten.
- **Renumbering.** Git sees a renumbered provision as one line removed and another added. The reader follows a provision through renumbering by matching its wording, and keeps its authors.
- **Word-level authorship.** \`git blame\` works line by line, so a provision amended by two laws is credited to the later one. The reader colours each phrase by the Act that wrote it.
- **Effective dates by pattern.** Effective-date notes are read by pattern, and unusual wording falls back to the date of enactment, which is usually right and occasionally is not.
- **Adjusted dollar amounts.** The Code prints the dollar amounts Congress enacted. The Judicial Conference adjusts many of them every three years by a notice in the Federal Register under 11 U.S.C. §104, and the adjusted amounts are published in those notices and in the Code's notes, not in the text. The reader shows them beside the provisions they adjust.
- **Changes on a condition.** A change that takes effect only when an agency makes a determination is left out of the text until that happens.
- **Everything before 2017.** The first commit is the 2017 edition as printed, without authors.
- **Retroactive dates.** A few changes took effect on a date before the law was enacted. Their commits carry the in-force date, so on dates in between the text shows words that had not yet been enacted. Each such commit says when the law was enacted.

Each commit links to the law's own words, and for anything that matters the law itself should be read.

## How it is built

The history is generated from the same data and the same code as the reader, so the text in this repository on any date is the text the reader shows for that date. The build script, the code it runs and the data it reads are in [\`build/\`](build/), byte for byte. The build is deterministic, and rebuilding from that data gives the same commits with the same hashes. [REPRODUCE.md](REPRODUCE.md) records the sources, every command, the software, the decisions made by hand and what an AI model did and did not do. Once other repositories refer to this one, updates are added as new commits instead of rewriting it.

Built by [Lexifina](${SITE}). For corrections, open an issue.

## License

The text of the US Code is a work of the United States Government and is in the public domain. The history, commit messages and README are released under [CC BY 4.0](LICENSE.md).
`
}
