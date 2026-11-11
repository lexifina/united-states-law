# Git for the US Code

Part of [lexifina/global-law](https://github.com/lexifina/global-law), one git history for every country's law: this is the United States Code, which global-law reads at `united-states/federal/usc/`.

The text of 53 titles of the United States Code, among them title 26, the Internal Revenue Code, with a commit for each law on each day its changes to them took effect, since the 1994 edition (current through January 4, 1995), and for most of title 26 since the Internal Revenue Code of 1986 (October 22, 1986). **Each commit is a law taking effect.** Its author is the public law that made the change, and its date is the day the change came into force; before the 2017 edition, the day the law was enacted (see [Before 2017](#before-2017-the-annual-editions-from-1994)).

So the questions a lawyer asks of a statute become git commands:

| The question | The command |
| --- | --- |
| What did §1182 say on 1 May 2022? | `git show $(git rev-list -1 --before=2022-05-01T23:59:59Z main):title-11/1182.md` |
| Which law wrote each provision? | `git blame title-11/1182.md` |
| What changed between two dates? | `git diff $(git rev-list -1 --before=2019-12-31T23:59:59Z main) $(git rev-list -1 --before=2022-12-31T23:59:59Z main) -- title-11/1182.md` |
| Everything one law changed | `git log -p --author="Pub. L. 116-136"` |
| Every change to a section | `git log -p -- title-11/1182.md` |
| One law's changes, by tag | `git show law/117-151` (its latest in-force date) or `git show law/117-151@2022-06-21` |
| The most amended sections of a title | `git log --format= --name-only -- title-11 \| sort \| uniq -c \| sort -rn \| head` |
| The law in force on the day a printed version is current through | `git checkout edition-2022` or `git checkout release-point-119-73` |

Give the date with a time, as above. With a bare date git uses the current time of day, and every commit is stamped at noon UTC, so the answer for the day a law took effect would depend on when you ask. In PowerShell, put the revision in a variable first: `$r = git rev-list -1 --before=2022-05-01T23:59:59Z main; git show "$($r):title-11/1182.md"`.

A tag such as `edition-2019` is the law **in force** on the day that version is current through. It differs from the printed version wherever a change was printed before it took effect: the 2019 edition printed the Small Business Reorganization Act, which took effect in February 2020.

If you would rather not use a terminal, the same history has a reader at **[lexifina.com/watch/us-code](https://lexifina.com/watch/us-code)**: pick a date and read the text in force on it, see the Act behind each phrase in colour, and see what else in the title relies on a provision. For example, [11 U.S.C. §1182](https://lexifina.com/watch/us-code/title-11/1182).

## What is here

| Title | Name | Sections | Changes | Reader |
| --- | --- | ---: | ---: | --- |
| [Title 1](title-1/) | General Provisions | 39 | 7 | [Read it](https://lexifina.com/watch/us-code/title-1) |
| [Title 2](title-2/) | The Congress | 1548 | 718 | not yet in the reader |
| [Title 3](title-3/) | The President | 60 | 44 | [Read it](https://lexifina.com/watch/us-code/title-3) |
| [Title 4](title-4/) | Flag and Seal, Seat of Government, and the States | 47 | 8 | [Read it](https://lexifina.com/watch/us-code/title-4) |
| [Title 5](title-5/) | Government Organization and Employees | 1127 | 1182 | not yet in the reader |
| [Title 6](title-6/) | Domestic Security | 586 | 1270 | not yet in the reader |
| [Title 7](title-7/) | Agriculture | 2841 | 2465 | not yet in the reader |
| [Title 8](title-8/) | Aliens and Nationality | 332 | 217 | not yet in the reader |
| [Title 9](title-9/) | Arbitration | 33 | 7 | [Read it](https://lexifina.com/watch/us-code/title-9) |
| [Title 10](title-10/) | Armed Forces | 4417 | 14510 | not yet in the reader |
| [Title 11](title-11/) | Bankruptcy | 278 | 122 | [Read it](https://lexifina.com/watch/us-code/title-11) |
| [Title 12](title-12/) | Banks and Banking | 1913 | 854 | not yet in the reader |
| [Title 13](title-13/) | Census | 65 | 1 | [Read it](https://lexifina.com/watch/us-code/title-13) |
| [Title 14](title-14/) | Coast Guard | 759 | 2516 | not yet in the reader |
| [Title 15](title-15/) | Commerce and Trade | 2634 | 2149 | not yet in the reader |
| [Title 16](title-16/) | Conservation | 5033 | 3001 | not yet in the reader |
| [Title 17](title-17/) | Copyrights | 147 | 108 | [Read it](https://lexifina.com/watch/us-code/title-17) |
| [Title 18](title-18/) | Crimes and Criminal Procedure | 1330 | 529 | not yet in the reader |
| [Title 19](title-19/) | Customs Duties | 1054 | 912 | not yet in the reader |
| [Title 20](title-20/) | Education | 1762 | 1047 | not yet in the reader |
| [Title 21](title-21/) | Food and Drugs | 718 | 1162 | not yet in the reader |
| [Title 22](title-22/) | Foreign Relations and Intercourse | 3309 | 2700 | not yet in the reader |
| [Title 23](title-23/) | Highways | 153 | 676 | not yet in the reader |
| [Title 24](title-24/) | Hospitals and Asylums | 122 | 30 | not yet in the reader |
| [Title 25](title-25/) | Indians | 2366 | 562 | not yet in the reader |
| [Title 26](title-26/) | Internal Revenue Code | 1933 | 3075 | not yet in the reader |
| [Title 27](title-27/) | Intoxicating Liquors | 29 | 0 | not yet in the reader |
| [Title 28](title-28/) | Judiciary and Judicial Procedure | 766 | 90 | not yet in the reader |
| [Title 29](title-29/) | Labor | 766 | 346 | not yet in the reader |
| [Title 30](title-30/) | Mineral Lands and Mining | 640 | 257 | not yet in the reader |
| [Title 31](title-31/) | Money and Finance | 492 | 295 | not yet in the reader |
| [Title 32](title-32/) | National Guard | 73 | 31 | not yet in the reader |
| [Title 33](title-33/) | Navigation and Navigable Waters | 1530 | 2271 | not yet in the reader |
| [Title 34](title-34/) | Crime Control and Law Enforcement | 802 | 1584 | not yet in the reader |
| [Title 35](title-35/) | Patents | 168 | 12 | [Read it](https://lexifina.com/watch/us-code/title-35) |
| [Title 36](title-36/) | Patriotic and National Observances, Ceremonies, and Organizations | 1172 | 281 | not yet in the reader |
| [Title 37](title-37/) | Pay and Allowances of the Uniformed Services | 214 | 581 | not yet in the reader |
| [Title 38](title-38/) | Veterans' Benefits | 1155 | 1690 | not yet in the reader |
| [Title 39](title-39/) | Postal Service | 175 | 56 | [Read it](https://lexifina.com/watch/us-code/title-39) |
| [Title 40](title-40/) | Public Buildings, Property, and Works | 452 | 181 | not yet in the reader |
| [Title 41](title-41/) | Public Contracts | 241 | 169 | not yet in the reader |
| [Title 42](title-42/) | The Public Health and Welfare | 8131 | 8466 | not yet in the reader |
| [Title 43](title-43/) | Public Lands | 1349 | 456 | not yet in the reader |
| [Title 44](title-44/) | Public Printing and Documents | 349 | 101 | not yet in the reader |
| [Title 45](title-45/) | Railroads | 258 | 64 | not yet in the reader |
| [Title 46](title-46/) | Shipping | 1036 | 1403 | not yet in the reader |
| [Title 47](title-47/) | Telecommunications | 428 | 491 | not yet in the reader |
| [Title 48](title-48/) | Territories and Insular Possessions | 515 | 132 | not yet in the reader |
| [Title 49](title-49/) | Transportation | 1335 | 2276 | not yet in the reader |
| [Title 50](title-50/) | War and National Defense | 1372 | 2671 | not yet in the reader |
| [Title 51](title-51/) | National and Commercial Space Programs | 247 | 87 | not yet in the reader |
| [Title 52](title-52/) | Voting and Elections | 171 | 22 | not yet in the reader |
| [Title 54](title-54/) | National Park Service and Related Programs | 366 | 99 | not yet in the reader |

Each section is one Markdown file, `title-<n>/<section>.md`, with one provision per line, so `git blame` names a law for every paragraph, subparagraph and clause. The history covers the annual editions from 1994 to 2024 and the release points since, up to Pub. L. 119–134 (for title 26, Pub. L. 119–138; for the titles added on 2026-11-10, Pub. L. 119–138). There are 6,587 commits.

## Before 2017: the annual editions from 1994

Since 10 November 2026 each title's history starts with the earliest annual edition GovInfo publishes: the **1994
edition, current through January 4, 1995** (laws enacted through that day). Titles 7, 28 and 39 start with the 1995
edition (January 16, 1996), because GovInfo has no 1994 edition of them; titles 51, 52 and 54 start with the first edition
that has them (2011, 2014, 2014). Title 34, which the Law Revision Counsel made in 2017 from sections of title 42, starts
with the 2017 edition: its sections' earlier text is in title 42's history. The first commit of each title is that edition
as printed, under the edition's name: lines first seen there are credited to the edition, not to the Acts that wrote
them, which each section's source credit lists.

**Title 26 from 1986.** Since 11 November 2026, 1,161 of title 26's 1,710 sections start earlier, with the Internal
Revenue Code of 1986 as it stood on October 22, 1986, the day the Tax Reform Act of 1986 (Pub. L. 99-514) was enacted.
That text is reconstructed, not printed: each section is the 1994 edition's text with every amendment its notes record
from laws enacted after that day reversed, newest first ("substituted X for Y" back to Y, inserted words taken out,
struck words put back beside the words the note names, added provisions taken out). 1,012 sections had no such
amendment; 149 were taken back through every one, and get a commit for each of those laws, dated by enactment and saying
it was reconstructed from the 1994 edition's amendment notes (trailer `Reconstructed-from: 1994`). A section a later
law added comes in with that law. The other 549 sections, whose notes could not all be reversed, start with the 1994
edition as before. The first commit, "The Internal Revenue Code of 1986 as of October 22, 1986", is the start of this
record for those sections, not their author. A random sample of 30 reversed amendments was checked against the amending
laws' own text in the Statutes at Large (GovInfo, volumes 101 to 108): 14 confirmed, 16 not verifiable by text search
(the scanned volumes' text is OCR, the notes paraphrase the instruction, or the law's pages could not be located), 0
contradicted.

Between consecutive editions up to 2017 the record is built from the editions themselves, because public laws before
the 113th Congress are not published as structured text and cannot be carried out by replay:

- **Laws.** A section that changed between two editions is credited to the public laws the newer edition names for it
  and the older one did not: in its source credit, its amendment notes (entries the newer edition added) or, for a
  section taken out of the Code, the bracketed notice that replaces it ("[§54. Repealed. Pub. L. 115–97, ...]"). Where
  several laws are new, each changed run of lines goes to the law whose amendment note quotes the new words, else
  names the provision, else amends the section as a whole. One commit per law, as from 2017 on; each says
  "Publisher's note only" and quotes the notes it relied on.
- **Dated by enactment.** These commits are dated the day the law was enacted, not the day its change took effect
  (effective-date notes are not read for this part of the record), and say so. A change enacted before the older
  edition's cutoff but not printed in it is dated the day after that cutoff.
- **Printed text differs.** A change no law could be matched to is committed under the newer edition's name on the day
  that edition is current through, with the reason for each section: the notes name no new law, or several new laws
  and the words could not be matched to one of them. Most are editorial.
- **Typography follows the latest printing.** The editions change typography now and then without changing the words
  (fractions as "½" from 2011, curly apostrophes from 2013). Where an edition prints the same words as the next with
  other quotation marks, apostrophes, fractions or spacing, the later form is used, so a change of typesetting does not
  show as a change to the law. The words are the edition's own.
- **The 2017 boundary.** Each title's block ends at exactly the text the 2017 edition commit below starts from, so those
  commits change nothing for the files their block already holds.

Across the 52 titles with a record before 2017: 5,867 commits before 2017; 49,516 changes to a section credited to a law,
22,470 to an edition, 405 in part. `build/history-2026-11-11/` has the code, the list of every edition used (URL, sha256,
size, cutoff), the per-title figures, the Statutes at Large sample and the map from earlier commit hashes to these ones
(`build/history-2026-11-10/` has the first version).

**Fixed on 11 November 2026.**

- **Paragraphs missing from 2017 on.** From the 2012 edition on, GovInfo prints some paragraphs with a `style`
  attribute (`<p class="statutory-body-block-2em" style="...">`), and the parser that built the history from 2017 skipped
  them. They are now in every commit, before and after 2017: 652 paragraphs in title 26 in the 2017 edition, for example
  the last sentence of 26 U.S.C. §21(b)(2)(A) ("Such term shall not include any amount paid for services outside the
  taxpayer's household at a camp where the qualifying individual stays overnight."). In the commits from 2017 each
  missing run of lines was put back where the printed version current on the commit's date has it, matched by the lines
  around it; 16 runs had no unique place and were left out. Today's text gained 1,258 lines in 667 files and lost none.
- **Sections moved in from another title.** A section the Law Revision Counsel moved into a title editorially ("formerly
  classified to ...") is now credited to the edition that first prints it there, not to a law that only amended it
  (1,148 sections).
- **Title 34** has no record before 2017 (see above).

**Known problems.**

- 53 sections whose notes say they were classified elsewhere before are still credited to the law that added them where
  they are (some rightly: a law that enacted a title as positive law moved them).
- In 94 files the text of the 2017 edition commits differs from the printed 2017 edition for other reasons (for example a
  later law the first build already applied); the last commit before 2017 brings each such file to that text and says so.

## Titles added later: read by date, not by position

Title 26 (the Internal Revenue Code) and three sections of title 17 (§104A, §106A and §121A, which the first build left
out because their numbers carry a capital letter) were added after the rest, on 2026-11-09, as **end blocks**: each block
starts with the text of the 2017 edition, dated January 12, 2018, followed by one commit for each law on each day its
changes took effect. History here is only ever added to, never rewritten, so these commits sit after commits with later
dates. Two consequences:

- **Ask per file.** `git rev-list -1 --before=DATE main` picks the last commit before DATE in the whole log, which for
  the other titles is fine but for title 26 lands in the wrong block. Name the file, and git walks only its own commits:
  `git show $(git rev-list -1 --before=2022-05-01T23:59:59Z main -- title-26/1.md):title-26/1.md` (in PowerShell:
  `$r = git rev-list -1 --before=2022-05-01T23:59:59Z main -- title-26/1.md; git show "$($r):title-26/1.md"`).
  `git log`, `git blame` and `git log -p` on a file are unaffected.
- **Tags.** The tags (`edition-*`, `release-point-*`, `law/*`, `data-*`) were made before 10 November 2026 and point at the
  commits of the history as it was then, before the record from 1994 was added; that history is kept as the branch
  `archive/main-before-history-2026-11-10` (and the first version of the record from 1994 as
  `archive/main-before-rewrite2-2026-11-11`), and `build/history-2026-11-11/old-to-new.tsv` maps the commits of both to the
  commit with the same change here. The `edition-*` and `release-point-*` tags were made before title 26 was added and do not include it. Law
  tags (`law/<pl>`) for laws that also changed the earlier titles point at their earlier commits; tags for laws first
  seen in title 26 point at title 26 commits.

The blocks start at `743cf4f` (The 2017 edition of the US Code, title 17: §104A, §106A, §121A), `0e2c79f` (The 2017 edition of the US Code, title 26). `corpus.json` lists them under `end_blocks`. (Commit hashes changed on 10 and 11 November 2026, when the record before 2017 was put in front of this history and then corrected; see CHANGES.md.)

The title 26 block's first commit gave the 2017 edition as printed. The commit after it, `212be7f` (`Kind:
correction`, `Corrects: dea7531…`, which is `0e2c79f` now, `In-force: 2018-01-12`), restates the text in force that day: 50 sections where Tax
Cuts and Jobs Act amendments (and three single changes by other laws) were already in force but not yet printed. Read
January 12, 2018 from it.

Titles 2, 5, 6, 7, 8, 10, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52 and 54 were added on 2026-11-10 as one more end block, `a608029` (The 2017 edition of the US Code, titles 2, 5, 6, 7, 8, 10, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 54), built the same way: the text in force on January 12, 2018, then one commit for each law on each day its changes took effect. Read them per file, as above.

### Tax law: dates and scope

Most tax amendments apply "to taxable years beginning after" a date, not from a date. As for every title, a commit is
dated the day the change came into force: the date the law or its effective-date note gives, or, where it gives none, the
date of enactment. The years a change applies to are kept as `Applies:` lines (`Applies: 26 U.S.C. §1(j) |
commenced-after 2017-12-31`, where "commenced" means the taxable year, plan year or other period the note names begins),
with the note's own words in the commit message. The text in each file is the text in force on the date; it is not
rewritten for the taxable years a change reaches.

## Three dates, and the one we use

Every change has at least three dates: when the law was enacted, when the change took effect, and when it first appeared in a printed version of the Code. They are often far apart. An amendment can be printed months before it takes effect, and can take effect before the next version prints it.

Commits are dated when a change **took effect**, because that is the date that decides which text governs a set of facts. Each commit message carries the other two (`Enacted:` and `Printed-in:`) and says why the change took effect when it did: a date in the amending provision, an effective-date note, or, where neither says anything, the date of enactment, which is the default rule for federal statutes.

One section shows why this matters. The definition of a small business debtor in [11 U.S.C. §1182(1)](https://lexifina.com/watch/us-code/title-11/1182) has had five different texts since 2019. A temporary $7.5 million debt limit lapsed in March 2022 and a new Act restored it in June 2022, reaching back to cases filed in between. `git log -p -- title-11/1182.md` shows each step on the day it took effect.

## How the history is checked

Comparing two printed versions shows *what* changed but not *why*. So for each pair of versions we took the public laws enacted in between, carried out their amending instructions ("by striking … and inserting …") on the older text in date order, and compared the result with the newer version. Of 365 changes, 361 reproduced the next printed version exactly. Every commit says how its change was confirmed:

- **Confirmed by replay.** Carrying out the law's instructions gives the printed text word for word.
- **Partly confirmed**, or **publisher's note only.** The law was found but its instructions could not all be carried out, so the change rests partly or wholly on the publisher's amendment note.

One kind of commit is not a law:

- **Printed text differs.** Where a newly printed version reads differently and no law taking effect that day accounts for it, the difference is committed under that version's name on the day it is current through. Most are editorial; a few are changes the record could not date. They are kept visible instead of being folded into a law's commit.

## What "author" means here

The author of a line is the **enacted law** that wrote it, not the legislator who drafted or proposed it. This history covers the Code as enacted. It does not cover bills, amendments that failed, or who voted for what.

## What it does not show

- **Court decisions.** A provision a court has held unconstitutional stays in the text, because courts do not change the text of the Code.
- **A law reaching back.** When a law applies to cases from before it was enacted, the commit message says so (`Applies to …`), but the text on the earlier dates is not rewritten.
- **Renumbering.** Git sees a renumbered provision as one line removed and another added. The reader follows a provision through renumbering by matching its wording, and keeps its authors.
- **Word-level authorship.** `git blame` works line by line, so a provision amended by two laws is credited to the later one. The reader colours each phrase by the Act that wrote it.
- **Effective dates by pattern.** Effective-date notes are read by pattern, and unusual wording falls back to the date of enactment, which is usually right and occasionally is not.
- **Adjusted dollar amounts.** The Code prints the dollar amounts Congress enacted. The Judicial Conference adjusts many of them every three years by a notice in the Federal Register under 11 U.S.C. §104, and the adjusted amounts are published in those notices and in the Code's notes, not in the text. The reader shows them beside the provisions they adjust.
- **Changes on a condition.** A change that takes effect only when an agency makes a determination is left out of the text until that happens.
- **Everything before 1995** (before October 22, 1986 for most of title 26). The first commit of each title is the
  earliest GovInfo edition as printed (1994 for most titles), or for title 26 the reconstructed 1986 Code, without authors.
- **Effective dates before 2017.** Changes before the 2017 edition are dated by enactment, and are not confirmed by replay.
- **Retroactive dates.** A few changes took effect on a date before the law was enacted. Their commits carry the in-force date, so on dates in between the text shows words that had not yet been enacted. Each such commit says when the law was enacted.

Each commit links to the law's own words, and for anything that matters the law itself should be read.

## How it is built

The history is generated from the same data and the same code as the reader, so the text in this repository on any date is the text the reader shows for that date. The build script, the code it runs and the data it reads are in [`build/`](build/), byte for byte. The build is deterministic, and rebuilding from that data gives the same commits with the same hashes. [REPRODUCE.md](REPRODUCE.md) records the sources, every command, the software, the decisions made by hand and what an AI model did and did not do. Once other repositories refer to this one, updates are added as new commits instead of rewriting it. The exceptions so far were decided by the owner: on 10 November 2026 the record from 1994 was put in front of the history, with the same text at every commit from 2017 on, and on 11 November 2026 it was corrected and the paragraphs the first build had dropped were put back in every commit (see CHANGES.md).

Built by [Lexifina](https://lexifina.com). For corrections, open an issue.

## Updates, links and related work

- [CHANGES.md](CHANGES.md): what changed in how this history is collected, recorded and checked, and when. Since 10 November 2026 the history covers every title of the Code: titles 1 to 54 (title 53 is reserved and has no sections). The appendices to titles 5, 11, 18, 28 and 50 are not included.
- [REPRODUCE.md](REPRODUCE.md): the sources, every command, the software, and what AI models did and did not do.
- The reader: [lexifina.com/watch/us-code](https://lexifina.com/watch/us-code).
- The post that explains the design: [Git for the US Code](https://lexifina.com/blog/git-for-the-us-code), and its [discussion on Hacker News](https://news.ycombinator.com/item?id=50268380).
- The film of the reader: [YouTube](https://youtu.be/cbds9FC4IDs).
- [lexifina/global-law](https://github.com/lexifina/global-law): this history alongside Lexifina's other law repositories (the German Basic Law, UK law, Swiss law and more), with one changelog of findings for all of them. Private for now.
- Lexifina's working notes on git for law (for members of the Lexifina organisation): the [global git-law tracker](https://claude.ai/artifact/KiqJgRjPMc88zFvbvDoFMr), the [research on official legal sources for every country](https://claude.ai/artifact/DdS9F6yqpPZtV2i7FGQhYZ), and the [census of git-for-law projects](https://claude.ai/artifact/7vD8b7fJzEnCumUoLvi5Dh).

## License

The text of the US Code is a work of the United States Government and is in the public domain. The history, commit messages and README are released under [CC BY 4.0](LICENSE.md).
