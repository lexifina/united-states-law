// Word-level spans between two strings, as segments. Used by the diff views in the browser and by the step view, whose
// rows are worked out when the page is built.
import { diff } from '../../../tools/_engine/diff'

export type Segment = { t: 'eq' | 'del' | 'ins'; s: string }

const tokens = (s: string) => s.match(/\s+|[\w$§%]+|[^\w\s]/g) ?? []

export function words(a: string, b: string): Segment[] {
  const ta = tokens(a), tb = tokens(b), out: Segment[] = []
  for (const o of diff(ta, tb)) {
    if (o.op === 'eq') out.push({ t: 'eq', s: ta.slice(o.aStart, o.aEnd).join('') })
    else if (o.op === 'del') out.push({ t: 'del', s: ta.slice(o.aStart, o.aEnd).join('') })
    else out.push({ t: 'ins', s: tb.slice(o.bStart, o.bEnd).join('') })
  }
  return out
}
