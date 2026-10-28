// REPRODUCE.md for the US Code git history (us-code-git.ts): how it was made, from what, with which software, and what
// an AI model did and did not do. The figures and hashes are computed by the build; the rest is the record.
import { formatDate } from '../app/watch/us-code/_data/load'

export interface ReproduceInfo {
  built: string
  lastLaw: string
  lawCommits: number
  sections: number
  titles: number[]
  editions: { count: number; fetched: string }
  releasePoints: { count: number; fetched: string }
  laws: { count: number; fetched: string }
  notices: number
  generated: string
  methodVersion: string
  summaries: { changes: number; changesByModel: number; laws: number; lawsByModel: number }
  dataSha256: string
  dataFiles: number
  blobs: { rel: string; blob: string }[]
}

export function reproduce(i: ReproduceInfo): string {
  return `# How this history was made, and how to make it again

This file records exactly how the repository was built: the sources, the commands, the software, the decisions made by hand, and what an AI model did and did not do. The script that made the history, the code it runs and the data it reads are in [\`build/\`](build/), byte for byte, so anyone with Node.js and git can rebuild it and check it.

## Short version

\`\`\`sh
git clone https://github.com/lexifina/us-code-history && cd us-code-history/build
sha256sum -c DATA-SHA256SUMS                          # the data is the data this history was built from
npx jiti@2.6.1 scripts/us-code-git.ts ../../rebuilt   # rebuild the whole history into an empty folder
git -C ../../rebuilt log --format=%H                  # the same commits, with the same hashes
\`\`\`

The last law commit is \`${i.lastLaw}\`. A rebuild from \`build/\` reproduces it, and the ${i.lawCommits - 1} commits before it, hash for hash, on any day and in any time zone: every date in the history comes from the data, and the documentation commit is dated ${formatDate(i.built)}, the day the data was built. \`npx jiti scripts/us-code-git-check.ts ../../rebuilt\` then checks every change against the text on the day it took effect.

## Sources

All legal text, and everything about each change, comes from official publishers of US law. Nothing was typed in, and no AI model wrote or edited any of it.

| What | Where | Documents | Retrieved |
| --- | --- | ---: | --- |
| Annual editions of each title, HTML | GovInfo, \`https://www.govinfo.gov/content/pkg/USCODE-<year>-title<n>/html/USCODE-<year>-title<n>.htm\` | ${i.editions.count} | ${i.editions.fetched} |
| Release points since the last edition, each current through a named public law | Office of the Law Revision Counsel, \`https://uscode.house.gov/download/releasepoints/us/pl/<congress>/<law>/htm_usc<n>@<congress>-<law>.zip\` | ${i.releasePoints.count} | ${i.releasePoints.fetched} |
| Each public law's text, with its amending instructions | GovInfo, \`https://www.govinfo.gov/content/pkg/PLAW-<congress>publ<n>/uslm/PLAW-<congress>publ<n>.xml\` | ${i.laws.count} | ${i.laws.fetched} |
| Judicial Conference notices adjusting dollar amounts (11 U.S.C. §104) | the Federal Register, through GovInfo | ${i.notices} | with the editions |

Each document was requested once and cached, with a pause of a second between requests and the user agent \`Mozilla/5.0 (compatible; Lexifina US Code history; +https://lexifina.com/watch)\`. Retries after an error are not counted above. The data records each document's URL, its sha256 and when it was fetched. For each document the build also asked the Internet Archive's availability API (\`https://archive.org/wayback/available\`) for an archived copy, and records the answer.

The adjustment notices are used by the reader on lexifina.com, not by this history: the Code prints the amounts Congress enacted.

## The build, step by step

These commands made this repository, in order.

1. **The data.** For each title (${i.titles.join(', ')}), Lexifina's backend ran \`python -m services.us_code_history.build --title <n> --summaries\`, with its defaults: the annual editions from 2017 to 2024, then every release point since. It ran in Lexifina's backend container, on Python 3.14.10. The code is in Lexifina's own repository at \`src/backend/services/us_code_history\` and is not published. It wrote one folder per title, built ${i.generated} (method version ${i.methodVersion}).
   - For each pair of consecutive versions, it finds the sections that changed and gathers the public laws enacted in between.
   - It carries out their amending instructions on the older text in date order, and compares the result with the newer version.
   - Each instruction becomes one change record: the provision before and after, the law, the dates, how far the replay matched, and the publisher's notes.
   - It reads each change's in-force date from the amending provision, an effective-date note, or the date of enactment.
2. **Copy into the site.** \`node scripts/sync-us-code-history.mjs\` copied the build into Lexifina's website at \`app/watch/us-code/_data\`. That folder is \`build/app/watch/us-code/_data\` here: ${i.dataFiles} files, listed with their sha256 in \`build/DATA-SHA256SUMS\`. The sha256 of that list is \`${i.dataSha256}\`.
3. **This history.** From the website's folder, \`npx jiti scripts/us-code-git.ts ../../us-code-history\` wrote the ${i.lawCommits} commits of the history, then one commit with the README, the licence, this file and \`build/\`.
4. **The check.** \`npx jiti scripts/us-code-git-check.ts ../../us-code-history\` compared every change record with the history.
   - The text after each change is in the file on the day it took effect, and the text before it was there the day before.
   - Where several instructions change one provision on the same day, only the last is checked against that day.
   - Every tagged version is compared with the printed text.
   - Run on 28 October 2026, all 274 checkable changes passed, after allowing for typography (the laws write "COVID-19" and "Pub. L. 105-277" with hyphens, the printed Code with en dashes). The tags matched the printed versions except where the README explains they differ.
5. **Publish.** \`git push\` to GitHub.

## Software

| Step | Software |
| --- | --- |
| The data (step 1) | Python 3.14.10 with httpx, in Lexifina's backend container |
| This history (steps 3 and 4) | Node.js 24.22.1, jiti 2.6.1 to run TypeScript, git 2.46.0, on Windows 11 |

The history build uses only Node's own modules and git. It makes no network requests.

The files under \`build/\`, with their git blob hashes:

| File | Git blob |
| --- | --- |
${i.blobs.map((b) => `| \`${b.rel}\` | \`${b.blob}\` |`).join('\n')}

They are the same files as in Lexifina's website repository, at the same paths.

## How the text and the commits are derived

Everything below is done by \`build/scripts/us-code-git.ts\`, deterministically.

- **Text.** A section's text on a date is worked out by the same code as the reader on lexifina.com (\`build/app/watch/us-code/_components/onDate.ts\`):
  - It starts from the latest version printed by that date.
  - It undoes any change printed but not yet in force, and applies any change in force but not yet printed.
  - Where one printed version holds several changes to a provision, it replays them one at a time up to the first not yet in force.
- **Files.** There is one Markdown file per section, \`title-<n>/<section>.md\`. Each provision is on its own line, nested by its level. Text outside any numbered provision is a paragraph.
- **Commits.** There is one commit for each law on each day its changes took effect.
  - The author is the law, \`Pub. L. <congress>-<number> (<short title>)\`, at an address ending \`.invalid\`.
  - The author and committer dates are noon UTC on the day the changes took effect. The committer is \`Lexifina <us-code-history@lexifina.com>\`.
  - The message lists each change with its status, a one-sentence summary, the instruction and a link to the reader, then the trailers \`Law:\`, \`Enacted:\`, \`In-force:\`, \`Printed-in:\`, \`Source:\` and \`Reader:\`.
  - Text that changed in a newly printed version with no law taking effect that day goes in a commit of its own, named after that version.
- **Tags.** \`edition-<year>\` and \`release-point-<congress>-<law>\` mark the law in force on the day each printed version is current through.

## Decisions made by hand

These choices were made when the build was written, after looking at the data. They are in the code and can be changed there.

1. **Commits are dated the day a change took effect**, not the day it was enacted or printed. Noon UTC keeps the day the same in every time zone.
2. **A few changes took effect before their law was enacted.** Their commits keep the in-force date, and the commit says when the law was enacted.
3. **Dollar adjustments are not applied to the text.** The Code prints the dollar amounts Congress enacted, and the triennial adjustments appear in the Federal Register and in the Code's notes. The adjustment data also lists the whole chain of earlier notices under the 2022 notice, so applying it would give wrong amounts.
4. **A change that waits on a condition is left out of the text.** One change to 11 U.S.C. §1325 takes effect only when the Small Business Administration makes a determination.
5. **Replayed text is normalised to the printed Code's form.** Text rebuilt from a law's own words uses curly quotes, and these become straight quotes, as the printed Code has them. A space after a heading's dash is removed. Without this, a date between two printed versions would look like a change.
6. **Unexplained differences get their own commits.** Two printed versions read differently with no law taking effect that day: 17 U.S.C. §114, where a repeal note was added, and 11 U.S.C. §1325. Those differences are committed under the version's name. One known fault is there: in §1325, the change on a condition hides a sunset in force on 27 December 2022, so that change appears in the commit for the 2022 edition. The reader has the same fault.
7. **Section headings follow their own changes.** Ten headings were changed by law. Each takes effect with its law.
8. **The history stops on the day the data was built**, ${formatDate(i.built)}. The documentation commit is dated that day too.

## What AI models did

**This repository** was built on 28 October 2026 in **Claude Code**, Anthropic's coding tool, by the model **Claude Opus 5.5** (model id \`claude-opus-5-5\`). It worked from a goal set by the user at Lexifina: to publish a git repository of the US Code history alongside the reader, applying the design argued for on lexifina.com. The model:

- wrote \`build/scripts/us-code-git.ts\`, \`us-code-git-check.ts\`, \`us-code-git-license.ts\` and \`us-code-git-reproduce.ts\`, the README, this file and the licence;
- moved the reader's text-on-a-date logic into \`onDate.ts\`, so the website and this history share it;
- ran the commands above and tested the result. That covered the check, a rebuild compared hash for hash, the README's commands in bash and PowerShell, GitHub's rendering, and the current text of two sections against Cornell's Legal Information Institute.

Testing found that every file was nested one level too shallow, and that was fixed before this file was written. The code that builds the data (step 1) and the reader were written earlier, in Claude Code sessions with the same model.

**The data** has one place where a language model wrote text: the one-sentence summary of each change, and of each law, in the commit messages.

- ${i.summaries.changesByModel} of the ${i.summaries.changes} change summaries, and ${i.summaries.lawsByModel} of the ${i.summaries.laws} law summaries, were written when the data was built, by the backend's secondary model. On the build dates that was configured as OpenAI's \`gpt-5.4-mini\`, with \`gpt-5.4-nano\` as a fallback. The data does not record which of the two answered each request.
- Each summary was checked by code before it was kept. Every number, dollar amount and quotation in it had to appear in the change's before or after text or in the law's instruction, and every change it cites had to exist.
- A summary that failed was replaced by a sentence written by a rule from the replayed operations. The rest of the summaries were written that way.
- The data marks each summary's source: \`model, checked\` or \`rule\`.

No model wrote or edited any legal text. Every word of every section is copied by code from GovInfo and the Law Revision Counsel. Every date, every law and every status comes from the publishers' text or from the replay of a law's own instructions. No model is called when this history is built or checked, and rebuilding it needs no model and gives the same result.

The user decided what was in scope and whether the repository is public. The work has not been reviewed line by line by a lawyer. As the README says, for anything that matters the law itself should be read.

## Changes to this history after it was published

- **28 October 2026.**
  - The repository was published under \`alan-yahya\`, then made private on the user's instruction, then moved to the \`lexifina\` organisation.
  - It was rebuilt once that day to fix the nesting of provisions, which changed every commit hash.
  - Lexifina's global-law repository refers to it, so this file and \`build/\` were then added in a commit of their own, keeping the published commits' hashes. A full rebuild puts them in the documentation commit instead.
`
}
