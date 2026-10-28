// Reads the US Code history build (scripts/sync-us-code-history.mjs copies it here) for the /watch/us-code pages.
// Pages are built ahead of time, so these files are read only during the build. Server code only (it reads files).
import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import { words } from '../_components/words'

const DIR = path.join(process.cwd(), 'app', 'watch', 'us-code', '_data')

export const REPO = 'https://github.com/lexifina/us-code-history'
// The repository is private for now; the site links to it only once it is public.
export const REPO_PUBLIC = false

export interface Segment { t: 'eq' | 'del' | 'ins'; s: string }
export interface OpRecord { kind: string; [key: string]: unknown }

const q = (v: unknown) => {
  const s = String(v ?? '')
  return `“${s.length > 90 ? `${s.slice(0, 90)}…` : s}”`
}

// One step of an instruction, as a plain sentence. Steps that only narrow where the instruction applies return null.
export function stepLabel(o: OpRecord): string | null {
  switch (o.kind) {
    case 'replace': return `Struck ${q(o.old)} and inserted ${q(o.new)}.`
    case 'replace_all': return `Struck ${q(o.old)} each place it appears and inserted ${q(o.new)}.`
    case 'replace_to_end': return `Struck ${q(o.start)} and all that follows, and inserted ${q(o.new)}.`
    case 'replace_end': return o.new ? `Struck ${q(o.old)} at the end and inserted ${q(o.new)}.` : `Struck ${q(o.old)} at the end.`
    case 'insert_after': return `Inserted ${q(o.new)} after ${q(o.anchor)}.`
    case 'insert_before': return `Inserted ${q(o.new)} before ${q(o.anchor)}.`
    case 'delete': return `Struck ${q(o.old)}.`
    case 'append_text': return `Added ${q(o.new)} at the end.`
    case 'append_block': return 'Added new text at the end.'
    case 'replace_block': return 'Replaced the text with the text the law sets out.'
    case 'replace_provision': return `Replaced ${String(o.target)} with the text the law sets out.`
    case 'delete_provision': return `Struck ${String(o.target)}.`
    case 'insert_block_after': return `Inserted new text after ${String(o.sibling)}.`
    case 'redesignate': return `Renumbered ${(o.pairs as [string, string][]).map(([a, b]) => `${a} as ${b}`).join(', ')}.`
    case 'revert': return 'Restored the text as it read on the day before the law was enacted.'
    default: return null
  }
}

export interface ChangeRecord {
  id: string
  title: number
  section: string
  heading: string
  path: string
  kind: 'amended' | 'added' | 'removed' | 'rewritten' | 'redesignated' | 'restored' | 'sunset'
  part?: 'heading'
  edition_from: string
  edition_to: string
  law: string | null
  instruction: { id: string; label: string; text: string; ops: OpRecord[]; effective: string | null; timing: string } | null
  status: 'replayed' | 'partly replayed' | 'not replayed' | "publisher's note only" | 'unexplained'
  ops: { op: string; applied: boolean; detail: string }[]
  mismatch: string[]
  before: string
  after: string
  in_edition: string
  diff: Segment[]
  fingerprints: { before: string; after: string; edition_from: string; edition_to: string; law?: string }
  dates: { enacted: string | null; effective: string | null; effective_as_enacted?: string | null; effective_set_by?: string; edition_current_through: string; edition_year: number; edition?: string; recorded: string }
  publisher_notes: { year: number; location: string; text: string }[]
  date_notes: { kind: string; heading: string; text: string }[]
  summary: string
  summary_source: string
  ends?: string[]
  ended_by?: string[]
  changed_by?: { law: string; label: string; text: string }[]
  candidate_laws?: string[]
  proposed_cause?: { law: string; label: string; reason: string; source: string }
  applies?: Applies | null
}

// When a change came into force and what it applies to, read from the law's own words or the effective-date notes.
// basis: "law" (the amending provision dates itself), "note" (a date provision the publisher notes), "condition" (it
// waits on an event) or "enactment" (no other date is given, so it took effect when the law was enacted).
export interface Applies {
  in_force: { date: string | null; basis: 'law' | 'note' | 'condition' | 'enactment'; words: string; source: string; condition: string | null }
  to: { text: string; relation: string; date: string; words: string; source: string }[]
}

export interface Law {
  pl: string
  congress: number
  number: number
  title: string
  short_title: string
  approved: string
  bill: { type: string; number: string; congress: string; label: string; url: string | null } | null
  history: string[]
  affected: string[]
  url: string
  page: string
  sha256: string
  fetched_at: string
  wayback: string | null
  instructions: number
  unparsed: number
  records: string[]
  summary: string | null
  summary_source?: string
}

// A version of the title: an annual edition (key "2024") or a Law Revision Counsel release point (key "pl119-83"),
// which is current through a named public law.
export interface Edition {
  key: string
  label: string
  kind: 'edition' | 'release_point'
  year: number
  current_through: string
  through_law: string | null
  url: string
  page: string
  sha256: string
  fetched_at: string
  sections: number
  wayback: string | null
}
export interface Transition { from: string; to: string; window: [string, string]; sections_changed: string[]; laws: string[]; records: string[] }
export interface NotShown { law: string; label: string; section: string; path: string; text: string; reason: string; note: { heading: string; text: string; edition: string; edition_label?: string } | null }

export interface Meta {
  title: number
  title_name: string
  method_version: string
  generated_at: string
  editions: Edition[]
  transitions: Transition[]
  laws: Law[]
  counts: { records: number; by_status: Record<string, number>; sections_changed: number }
  not_shown: NotShown[]
}

export interface SectionLine { path: string; level: number; text: string }
export interface SectionVersion { editions: string[]; sha256: string | null; heading: string | null; lines: SectionLine[] }
// Where one version's change to a section took several instructions: the section before them, and the lines each
// instruction replaced, as [start, end, new lines] against the text before it.
export interface SectionReplay { from: string; to: string; start: SectionLine[]; steps: { record: string; edits: [number, number, SectionLine[]][] }[] }
export interface SectionFile {
  section: string
  heading: string
  source_credit: string
  versions: SectionVersion[]
  records: string[]
  blame: { path: string; record: string | null; law: string | null; edition: string | null }[]
  adjustments: { notice: string; citation: string; dated: string; effective: string; url: string; changes: { path: string; text: string }[] }[]
  replays?: SectionReplay[]
}
export interface SectionSummary { section: string; heading: string; changes: number; repealed: boolean }
export interface Correction { date: string; title?: number; record: string | null; text: string }

// Cached per file and re-read when the file changes, so a new sync shows up in a running dev server.
const cache = new Map<string, { mtime: number; data: unknown }>()
function read<T>(file: string): T {
  const full = path.join(DIR, file)
  const mtime = statSync(full).mtimeMs
  const hit = cache.get(file)
  if (hit && hit.mtime === mtime) return hit.data as T
  const data = JSON.parse(readFileSync(full, 'utf8'))
  cache.set(file, { mtime, data })
  return data as T
}

// ---- Titles ----

// The titles the record covers: one folder per title, title9, title11 and so on.
export function titles(): number[] {
  return readdirSync(DIR)
    .map((d) => d.match(/^title(\d+)$/)?.[1])
    .filter((d): d is string => Boolean(d))
    .map(Number)
    .sort((a, b) => a - b)
}

export const titleSlug = (t: number) => `title-${t}`
export function titleFromSlug(slug: string): number | undefined {
  const m = slug.match(/^title-(\d+)$/)
  return m && titles().includes(Number(m[1])) ? Number(m[1]) : undefined
}

// "Bankruptcy", from the title's own heading in the Code.
export function titleName(t: number): string {
  const name = meta(t).title_name
  if (!name || /^Title \d+$/.test(name)) return `Title ${t}`
  // The Code prints title names in capitals; small words stay lowercase after the first word.
  return name.replace(/(?!^)\b(And|Of|The|In|For|To|On|Or)\b/g, (w) => w.toLowerCase())
}

export const meta = (t: number) => read<Meta>(`title${t}/meta.json`)
export const records = (t: number) => read<ChangeRecord[]>(`title${t}/records.json`)
export const sections = (t: number) => read<SectionSummary[]>(`title${t}/sections.json`)
export const section = (t: number, n: string) => read<SectionFile>(`title${t}/sections/${n}.json`)
export const corrections = () => read<Correction[]>('corrections.json')
export const allRecords = () => titles().flatMap((t) => records(t))

export function record(t: number, id: string): ChangeRecord | undefined {
  return records(t).find((r) => r.id === id)
}

export function sectionNumbers(t: number): string[] {
  return sections(t).map((s) => s.section)
}

// ---- Addresses ----

export const titleHref = (t: number) => `/watch/us-code/${titleSlug(t)}`
export const sectionHref = (t: number, n: string) => `/watch/us-code/${titleSlug(t)}/${n}`
export const versionHref = (t: number, key: string) => `/watch/us-code/${titleSlug(t)}/versions/${key}`
export const changeHref = (r: { title: number; id: string }) => `/watch/us-code/${titleSlug(r.title)}/changes/${r.id}`
export const lawHref = (pl: string) => `/watch/us-code/laws/${pl}`

// ---- Laws, across titles ----

export interface LawInTitle { title: number; records: string[]; summary: string | null; summary_source?: string }
export interface LawAll extends Law { titles: LawInTitle[] }

// One entry per public law, with the changes it made in each title covered.
export function laws(): LawAll[] {
  const byPl = new Map<string, LawAll>()
  for (const t of titles()) {
    for (const l of meta(t).laws) {
      const entry = byPl.get(l.pl) ?? { ...l, titles: [] }
      entry.titles.push({ title: t, records: l.records, summary: l.summary, summary_source: l.summary_source })
      byPl.set(l.pl, entry)
    }
  }
  return Array.from(byPl.values()).sort((a, b) => a.approved.localeCompare(b.approved) || a.number - b.number)
}

export function law(pl: string): LawAll | undefined {
  return laws().find((l) => l.pl === pl)
}

export const lawChangeCount = (l: LawAll) => l.titles.reduce((n, t) => n + t.records.length, 0)

// ---- Versions of a title ----

export function version(t: number, key: string): Edition | undefined {
  return meta(t).editions.find((e) => e.key === key)
}

// "2024 edition" or "Release point 119-83", for headings and labels.
export function versionLabel(t: number, key: string): string {
  return version(t, key)?.label ?? key
}

// "the 2024 edition" or "release point 119-83", for use inside a sentence.
export function versionName(t: number, key: string): string {
  const e = version(t, key)
  if (!e) return key
  return e.kind === 'edition' ? `the ${e.year} edition` : `release point ${e.through_law}`
}

// "2021 to 2022 edition", or "2024 edition to release point 119-73" when a release point is involved.
export function versionSpan(t: number, from: string, to: string): string {
  const a = version(t, from)
  const b = version(t, to)
  if (a?.kind === 'edition' && b?.kind === 'edition') return `${a.year} to ${b.year} edition`
  return `${versionLabel(t, from)} to ${versionName(t, to).replace(/^the /, '')}`
}

export function versionOrder(t: number, key: string): number {
  return meta(t).editions.findIndex((e) => e.key === key)
}

export function publisherOf(e: Edition): string {
  return e.kind === 'edition' ? 'GovInfo' : 'the Law Revision Counsel'
}

// "the annual editions from 2017 to 2024 and the release points since, up to Pub. L. 119–124", for one title or all.
export function coverageText(t?: number): string {
  const all = (t === undefined ? titles() : [t]).flatMap((x) => meta(x).editions)
  const eds = all.filter((e) => e.kind === 'edition').map((e) => e.year)
  const rps = all.filter((e) => e.kind === 'release_point').sort((a, b) => a.current_through.localeCompare(b.current_through))
  const annual = `the annual editions from ${Math.min(...eds)} to ${Math.max(...eds)}`
  return rps.length ? `${annual} and the release points since, up to ${lawLabel(rps[rps.length - 1].through_law ?? '')}` : annual
}

export function lawLabel(pl: string): string {
  return `Pub. L. ${pl.replace('-', '–')}`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
}

export const KIND_LABEL: Record<ChangeRecord['kind'], string> = {
  amended: 'Amended',
  added: 'Added',
  removed: 'Removed',
  rewritten: 'Rewritten',
  redesignated: 'Renumbered',
  restored: 'Restored',
  sunset: 'Temporary change ended',
}

export const STATUS_LABEL: Record<ChangeRecord['status'], string> = {
  replayed: 'Confirmed by replay',
  'partly replayed': 'Partly confirmed',
  'not replayed': 'Not confirmed',
  "publisher's note only": "Publisher's note only",
  unexplained: 'Cause not found',
}

// Keeps a citation such as 101(51D)(B)(i) from breaking across lines.
export function tidy(text: string): string {
  return text.replace(/\)\(/g, ')\u2060(')
}

export function where(r: ChangeRecord): string {
  return `§${r.section}${r.path}${r.part === 'heading' ? ', heading' : ''}`
}

// "17 U.S.C. §115(d)(3)"
export function citeOf(r: ChangeRecord): string {
  return `${r.title} U.S.C. ${where(r)}`
}

export function causeLabel(r: ChangeRecord): string {
  if (!r.law) return 'Cause not found'
  return `${lawLabel(r.law)}${r.instruction ? `, ${r.instruction.label}` : ''}`
}


// ---- Step by step ----

export interface StepRow { kind: 'eq' | 'del' | 'ins' | 'fold'; level: number; text: string; segments?: Segment[]; count?: number }
export interface ReplayStep { record: string; href: string; cause: string; instruction: string; rows: StepRow[] }
export interface ReplayView { from: string; to: string; steps: ReplayStep[]; matches: boolean }

const CONTEXT = 1   // unchanged provisions shown on each side of a change; the rest fold away

// The rows one step changes, against the section as it read before that step: removed and added provisions, with the
// changed words marked where a provision was amended, between folds of the provisions it left alone.
function stepRows(before: SectionLine[], edits: [number, number, SectionLine[]][]): StepRow[] {
  const rows: StepRow[] = []
  const unchanged = (from: number, to: number, leading: boolean, trailing: boolean) => {
    const lines = before.slice(from, to)
    const head = leading ? 0 : Math.min(CONTEXT, lines.length)
    const tail = trailing ? 0 : Math.min(CONTEXT, lines.length - head)
    lines.slice(0, head).forEach((l) => rows.push({ kind: 'eq', level: l.level, text: l.text }))
    if (lines.length - head - tail > 0) rows.push({ kind: 'fold', level: 0, text: '', count: lines.length - head - tail })
    lines.slice(lines.length - tail).forEach((l) => rows.push({ kind: 'eq', level: l.level, text: l.text }))
  }
  let at = 0
  edits.forEach(([start, end, added], k) => {
    unchanged(at, start, k === 0, false)
    const removed = before.slice(start, end)
    // A provision amended in place is paired with its new text so the changed words show; runs of equal length pair
    // in order, others by designation.
    const match = (l: SectionLine, n: number, others: SectionLine[]) => (removed.length === added.length ? others[n] : others.find((o) => o.path && o.path === l.path))
    removed.forEach((l, n) => {
      const p = match(l, n, added)
      rows.push({ kind: 'del', level: l.level, text: l.text, segments: p ? close(l.text, p.text) : undefined })
    })
    added.forEach((l, n) => {
      const p = match(l, n, removed)
      rows.push({ kind: 'ins', level: l.level, text: l.text, segments: p ? close(p.text, l.text) : undefined })
    })
    at = end
  })
  unchanged(at, before.length, edits.length === 0, true)
  return rows
}

// Word-level spans between an old and a new provision, when they share most of their text; a provision replaced by
// different text reads better as one line removed and one added.
function close(a: string, b: string): Segment[] | undefined {
  const spans = words(a, b)
  const same = spans.reduce((n, x) => n + (x.t === 'eq' ? x.s.length : 0), 0)
  return same >= 0.5 * Math.max(a.length, b.length) ? spans : undefined
}

function applyEdits(lines: SectionLine[], edits: [number, number, SectionLine[]][]): SectionLine[] {
  const out = [...lines]
  for (const [start, end, added] of [...edits].reverse()) out.splice(start, end - start, ...added)
  return out
}

// The instructions behind one version's change to a section, applied one at a time to the earlier text, when there
// was more than one.
export function replayOf(r: ChangeRecord): ReplayView | undefined {
  const replay = section(r.title, r.section).replays?.find((x) => x.steps.some((s) => s.record === r.id))
  if (!replay) return undefined
  let text = replay.start
  const steps: ReplayStep[] = []
  let matches = true
  for (const s of replay.steps) {
    const rec = record(r.title, s.record)
    if (!rec) return undefined
    matches &&= rec.status === 'replayed'
    const ins = rec.instruction?.text ?? ''
    steps.push({
      record: rec.id,
      href: changeHref(rec),
      cause: causeLabel(rec),
      instruction: ins.length > 700 ? `${ins.slice(0, 700)}…` : ins,
      rows: stepRows(text, s.edits),
    })
    text = applyEdits(text, s.edits)
  }
  return { from: replay.from, to: replay.to, steps, matches }
}

// ---- When a change applies ----

// The date a change came into force: the structured date where there is one, else the law's own date, else enactment.
export function inForce(r: ChangeRecord): string | null {
  if (r.applies) return r.applies.in_force.date
  return r.dates.effective ?? r.dates.enacted
}

// "1 year after enactment, under Pub. L. 116–136, div. A, title I, §1113(b)(2)(B)": why a change came into force when it did.
export function inForceReason(r: ChangeRecord): string {
  const f = r.applies?.in_force
  if (!f) return ''
  if (f.basis === 'law') {
    const moved = r.dates.effective_set_by ? ` ${lawLabel(r.dates.effective_set_by)} later moved it from ${formatDate(r.dates.effective_as_enacted)}.` : ''
    return `The amending provision sets its own date.${moved}`
  }
  if (f.basis === 'note') return `Set by ${f.source}.`
  if (f.basis === 'condition') return `It takes effect when ${f.condition}, under ${f.source}.`
  return "Neither the law nor the publisher's notes give another date, so it took effect when the law was enacted."
}

// ---- Reading a section: dates, authorship and what relies on it ----

// One change to a section, as the section reader needs it in the browser.
export interface SectionChange {
  id: string
  href: string
  path: string
  heading: boolean
  from: string
  to: string
  law: string | null
  lawName: string
  enacted: string | null
  inForce: string | null
  condition: string | null
  scope: string[]
  added: string[]      // the words this change inserted, so a phrase can be traced to the right change
  summary: string      // what the change did, in a sentence
  kind: string         // "Rewritten", "Temporary change ended"
}

export function sectionChanges(t: number, n: string): SectionChange[] {
  const names = new Map(meta(t).laws.map((l) => [l.pl, l.short_title || l.title]))
  return records(t).filter((r) => r.section === n && r.law).map((r) => ({
    id: r.id,
    href: changeHref(r),
    path: r.path,
    heading: r.part === 'heading',
    from: r.edition_from,
    to: r.edition_to,
    law: r.law,
    lawName: names.get(r.law ?? '') ?? lawLabel(r.law ?? ''),
    enacted: r.dates.enacted,
    inForce: r.applies ? r.applies.in_force.date : (r.dates.effective ?? r.dates.enacted),
    condition: r.applies?.in_force.condition ?? null,
    scope: (r.applies?.to ?? []).map((x) => x.text),
    added: r.diff.filter((s) => s.t === 'ins').map((s) => s.s.trim()).filter(Boolean),
    summary: tidy(r.summary),
    kind: KIND_LABEL[r.kind],
  }))
}

// A provision elsewhere in the title that relies on another: it cites it ("as defined in section 101(51D)") or uses a
// term it defines ("small business debtor").
export interface Reliance {
  section: string
  heading: string
  path: string
  text: string
  target: string          // the provision relied on, as a path in the cited section ("(51D)"), "" for the section
  term?: string           // the defined term used, where the reliance is by term
}

const CITE = /\bsections? ((?:\d+[A-Za-z]?(?:\([^)\s]{1,6}\))*(?:,? (?:and|or|through) |, )?)+)/g
const ELSEWHERE = /^[^.;]{0,60}?\bof (?:title \d+|the [A-Z][\w-]*|this Act|such Act|Public Law|that Act)/

const reliesCache = new Map<number, { key: string; bySection: Map<string, Reliance[]> }>()

// Every reliance within a title, by the section relied on. Built from the latest text of each section.
function reliances(t: number): Map<string, Reliance[]> {
  const key = meta(t).generated_at
  const hit = reliesCache.get(t)
  if (hit && hit.key === key) return hit.bySection
  const bySection = new Map<string, Reliance[]>()
  const add = (n: string, r: Reliance) => {
    const list = bySection.get(n) ?? []
    if (!list.some((x) => x.section === r.section && x.path === r.path && x.target === r.target && x.term === r.term)) list.push(r)
    bySection.set(n, list)
  }
  const list = sectionNumbers(t)
  const numbers = new Set(list)
  const latest = (n: string) => {
    const s = section(t, n)
    const v = s.versions[s.versions.length - 1]
    return { heading: s.heading, lines: v?.lines ?? [] }
  }
  // Defined terms, from "The term “small business debtor” means". Single words ("person", "State") are left out:
  // they are used everywhere and would bury the useful links.
  const terms: { term: string; section: string; path: string; re: RegExp }[] = []
  for (const n of list) {
    for (const l of latest(n).lines) {
      for (const m of Array.from(l.text.matchAll(/\b[Tt]he terms? [“"]([^”"]{3,60})[”"]/g))) {
        const term = m[1].trim()
        if (term.split(/\s+/).length < 2) continue
        terms.push({ term, section: n, path: l.path, re: new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i') })
      }
    }
  }
  for (const n of list) {
    const { heading, lines } = latest(n)
    for (const l of lines) {
      for (const m of Array.from(l.text.matchAll(CITE))) {
        const after = l.text.slice((m.index ?? 0) + m[0].length)
        if (ELSEWHERE.test(after)) continue
        for (const c of Array.from(m[1].matchAll(/(\d+[A-Za-z]?)((?:\([^)\s]{1,6}\))*)/g))) {
          const target = c[1]
          if (target === n || !numbers.has(target)) continue
          add(target, { section: n, heading, path: l.path, text: l.text, target: c[2] })
        }
      }
      for (const d of terms) {
        if (d.section === n || !d.re.test(l.text)) continue
        add(d.section, { section: n, heading, path: l.path, text: l.text, target: d.path, term: d.term })
      }
    }
  }
  reliesCache.set(t, { key, bySection })
  return bySection
}

// What relies on a section, or on one provision of it (and the provisions inside it).
export function reliesOn(t: number, n: string, path = ''): Reliance[] {
  const all = reliances(t).get(n) ?? []
  if (!path) return all
  return all.filter((r) => r.target === path || r.target.startsWith(path) || (r.target !== '' && path.startsWith(r.target)))
}

// Changes to every section, small enough for the browser: used by followed sections.
export interface FollowIndex { [key: string]: { label: string; heading: string; href: string; changes: { id: string; date: string; href: string; where: string }[] } }
export function followIndex(): FollowIndex {
  const out: FollowIndex = {}
  for (const t of titles()) {
    const heads = new Map(sections(t).map((s) => [s.section, s.heading]))
    for (const r of records(t)) {
      const key = `${t}-${r.section}`
      const entry = out[key] ?? (out[key] = { label: `${t} U.S.C. §${r.section}`, heading: heads.get(r.section) ?? '', href: sectionHref(t, r.section), changes: [] })
      entry.changes.push({ id: r.id, date: inForce(r) ?? r.dates.edition_current_through, href: changeHref(r), where: where(r) })
    }
  }
  return out
}

// What relies on a section, as groups a reader can follow: one group per defined term or cited provision, each with
// the sections that use it, their headings and the words around the use.
export interface RelianceGroup {
  key: string
  term: string | null           // the defined term, or null where the group is a citation
  target: string                // the provision relied on, as a path ("(2)"), "" for the whole section
  sections: number              // how many different sections
  rows: { section: string; path: string; heading: string; href: string; before: string; match: string; after: string }[]
}

function around(text: string, re: RegExp): { before: string; match: string; after: string } {
  const m = re.exec(text)
  if (!m) return { before: '', match: '', after: text.length > 160 ? `${text.slice(0, 160)}…` : text }
  const start = Math.max(0, m.index - 70)
  const end = Math.min(text.length, m.index + m[0].length + 90)
  return { before: `${start > 0 ? '…' : ''}${text.slice(start, m.index)}`, match: m[0], after: `${text.slice(m.index + m[0].length, end)}${end < text.length ? '…' : ''}` }
}

export function relianceGroups(t: number, n: string, path = ''): RelianceGroup[] {
  const groups = new Map<string, RelianceGroup>()
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  for (const r of reliesOn(t, n, path)) {
    const key = r.term ? `term:${r.term}` : `cite:${r.target}`
    const g = groups.get(key) ?? { key, term: r.term ?? null, target: r.target, sections: 0, rows: [] }
    const re = r.term ? new RegExp(esc(r.term), 'i') : new RegExp(`sections? [^.;]{0,40}?\\b${esc(n)}${esc(r.target)}`, 'i')
    g.rows.push({ section: r.section, path: r.path, heading: r.heading, href: sectionHref(t, r.section), ...around(r.text, re) })
    groups.set(key, g)
  }
  const out = Array.from(groups.values())
  for (const g of out) g.sections = new Set(g.rows.map((x) => x.section)).size
  return out.sort((a, b) => b.rows.length - a.rows.length)
}
