# Changes and updates

How this history was made and changed, newest first. Each entry says what changed in how the data is collected, stored
or checked, and why. [REPRODUCE.md](REPRODUCE.md) has the exact commands and versions; Lexifina's global-law repository
keeps the log for every corpus (`CHANGELOG.md` there).

## 11 November 2026: corrections, and title 26 from 1986

**The history was rewritten once more** (the owner's decision), to make four corrections at once; every commit hash
changed again. The previous main is the branch `archive/main-before-rewrite2-2026-11-11` (`351e6ca`);
`build/history-2026-11-11/old-to-new.tsv` maps it and the history before 10 November to these commits.

- **Paragraphs put back.** The parser behind the history from 2017 skipped paragraphs GovInfo prints with a `style`
  attribute (from the 2012 edition on). They are now in every commit from 2012: in the commits from 2017 each was put back
  where the printed version current that day has it (1,575 file versions; 16 runs had no unique place). Today's text
  gained 1,258 lines in 667 files and lost none; title 26 gained 662 lines in 301 files.
- **Sections moved in editorially** are credited to the edition that first prints them in their new place, not as added
  by a law that only amended them (1,148 sections).
- **Title 34** has no record before 2017: GovInfo's earlier "title 34" is the old Navy title, repealed in 1956.
- **Title 26 from 1986.** 1,161 of 1,710 sections now start with the Internal Revenue Code of 1986 (October 22, 1986),
  reconstructed by reversing the 1994 edition's amendment notes: 1,012 had no later amendment, 149 were taken back
  through every one and get a commit per law (dated by enactment, marked `Reconstructed-from: 1994`). 549 sections whose
  notes could not all be reversed start with the 1994 edition as before. Sample check against the Statutes at Large: 14
  of 30 confirmed, 16 not verifiable by text search, 0 contradicted.

Before 2017: 5,867 commits; 49,516 section changes credited to a law, 22,470 to an edition, 405 in part.

## 10 November 2026 (later): the record before 2017

**Every title now starts with the 1994 edition** (current through January 4, 1995; titles 7, 28 and 39 with the 1995
edition, titles 51, 52 and 54 with their first edition). 5,893 commits before 2017, built from the 23 annual editions
GovInfo publishes for 1994 to 2016 and their own records: each change to a section between two editions is credited to
the public law the newer edition names for it (source credit, new amendment-note entries, or the notice that replaces a
repealed section), dated by enactment; changes no law could be matched to are committed as "Printed text differs" under
the edition. Typography follows the latest printing where the words are the same. 49,750 section changes credited to a
law, 23,306 to an edition, 522 in part.

**The history was rewritten once to do this**, on the owner's decision: these commits sit before the history from 2017,
which follows with the same authors, dates, messages and text at every commit, so the final text is unchanged (same tree,
`27abda94`), but every commit hash changed. The earlier history is the branch `archive/main-before-history-2026-11-10`
(`2d47734`); the tags still point into it; `build/history-2026-11-10/old-to-new.tsv` maps old commits to new.
Lexifina's global-law repository was re-pointed to the new history.

Found while building it, both pending a fix: the parser behind the history from 2017 skips paragraphs GovInfo prints with
a `style` attribute (from the 2012 edition on; 652 paragraphs in title 26, 749 files in all), and 390 sections moved in
from another title editorially are credited as added by a law that only amended them. The README's "Before 2017" section
has the details.

## 10 November 2026

**Titles 2, 5, 6, 7, 8, 10, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52 and 54** added as an end block: 55893 sections, 60544 change records, 15279 of them reproduced the next printed version exactly by carrying out the law's instructions. Built with the same code as title 26 (the four general fixes of 9 November). Added as new commits after the documentation; no earlier commit or tag changed.

## 9 November 2026

**Title 26, the Internal Revenue Code**, added as an end block: 1933 sections, 3075 change records from
44 public laws, 1757 of them reproduced the next printed version exactly by carrying out the law's
instructions. **Title 17 §104A, §106A, §121A** added as an end block (the Marrakesh Treaty Implementation Act's §121A,
confirmed by replay). Added as new commits after the documentation; no earlier commit or tag changed.

Fixed in how the data is collected (each a general rule; titles 9, 11 and 17 rebuilt with the same records as before,
plus §121A):
- **Section numbers with capital letters or hyphens** (25A, 199A, 4980H, 1400Z-2, 78a-1) were dropped by the edition
  parser, and a new section's number was lowercased (121a) or lost its hyphen. They are kept as the Code prints them.
- **Laws that amend the Internal Revenue Code by name.** Tax laws say "Section 1 is amended" under a rule that every
  amendment in a title "shall be considered to be made to a section or other provision of the Internal Revenue Code of
  1986", or "Section 45Q of the Internal Revenue Code of 1986" / "of such Code". These are now read as title 26.
- **A section added whole** by an instruction that names its neighbour ("inserting after section 121 the following:
  § 121A") is matched to the new section.
- **Word differences** are found line by line first, so long sections no longer take minutes each.

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
