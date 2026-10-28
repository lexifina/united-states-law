# Changes and updates

How this history was made and changed, newest first. Each entry says what changed in how the data is collected, stored
or checked, and why. [REPRODUCE.md](REPRODUCE.md) has the exact commands and versions; Lexifina's global-law repository
keeps the log for every corpus (`CHANGELOG.md` there).

## 28 October 2026

**The whole Code.** The history is being rebuilt with every title of the Code (1 to 54; 53 is reserved; the title
appendices are left out), from the 2017 editions to the latest release point. It replaces the nine-title history, so
every commit hash and tag changes: `git fetch --force --tags origin && git reset --hard origin/main`.

Fixed in how the data is collected and recorded:
- **Dollar adjustments.** The parser of the Code's "Adjustment of Dollar Amounts" notes ran one Federal Register entry
  into the next, filing every older notice under the newest (87 F.R. 6625). Each notice now keeps its own clauses.
- **Dollar adjustments as commits.** Each Judicial Conference notice under 11 U.S.C. §104 is an empty commit on its
  effective date (`Words-changed: no`) with one `Modifies:` line per provision, giving the amount that applies and the
  range it applies for (closed the day before the next notice). The files keep the amounts Congress enacted, as the
  printed Code does. `tools/uscode.py on` prints the adjusted amounts after the text.
- **Which cases a change applies to.** Every group of cases a law reaches is kept with all of its conditions
  (Pub. L. 117-151 §2(h)(2): cases commenced on or after 27 March 2020, and cases commenced between then and 21 June
  2022 still pending on that day). Effective-date notes are matched to the amendment they name, not to every change in
  the section (the CARES Act §1113(b)(1)(D)(i) note). A change known only from the publisher's note takes its law's
  note when that note is about one amendment (Pub. L. 118-42, §507). Commits carry one `Applies:` line per group.
- **Release points listed before they are published.** Release point 119-136 was listed while its files returned 404,
  and the build dropped it and the one before it. It now falls back to the newest release point that loads.
- **Several changes in one printed version.** Where a version holds a change waiting on a condition, a change in force
  and a sunset of the first (11 U.S.C. §1325 in 2022), the text on a date replays every step and shows the lines whose
  changes are in force. Before, everything after the first change not in force was dropped. The reader on lexifina.com
  uses the same code and has the same fix.
- **Publication gaps.** A section missing from one printed version but back in a later one, with no law removing it, is
  kept; it is not recorded as repealed and re-added.
- **Repealed sections** keep a file saying so, credited to the law that repealed them.
- **Markdown.** Formatting characters in the law's text are escaped, so "the symbol \*M\*" (17 U.S.C. §909) shows as
  written.

Added:
- `tools/uscode.py`: `on`, `diff`, `log` and `commit`, reading the history by each commit's `In-force:` date, so
  answers do not depend on time zone or time of day.
- `Applies:`, `Modifies:`, `Words-changed:` and `Consolidated:` trailers, in the shapes agreed with Lexifina's
  other law repositories.
- A tag check that compares headings as well as text, for every printed version, including those that changed nothing.

How it is built: the generator works one section at a time with a content store on disk and streams the commits into
one `git fast-import`; the data build runs as four workers on one queue. The same data still gives the same hashes.

**Nine titles.** The first history (titles 1, 3, 4, 9, 11, 13, 17, 35 and 39) was published, made private, moved to the
`lexifina` organisation, and rebuilt once to fix the nesting of provisions. REPRODUCE.md and `build/` were added in a
commit of their own. Testing then checked every change against the text on the day it took effect (274 of 274) and
every tag against the printed text.

## Why it exists

Readers of Lexifina's post on the US Code reader pointed out that its history could not be cloned. This repository is
the answer: the same history as the reader, as git, with the method written down.
