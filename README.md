# Git for the US Code

Part of [lexifina/global-law](https://github.com/lexifina/global-law), one git history for every country's law: this is the United States Code, which global-law reads at `united-states/federal/usc/`.

The text of 53 titles of the United States Code, among them title 26, the Internal Revenue Code, with a commit for each law on each day its changes to them took effect, since the 2017 edition. **Each commit is a law taking effect.** Its author is the public law that made the change, and its date is the day the change came into force.

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

Each section is one Markdown file, `title-<n>/<section>.md`, with one provision per line, so `git blame` names a law for every paragraph, subparagraph and clause. The history covers the annual editions from 2017 to 2024 and the release points since, up to Pub. L. 119–134 (for title 26, Pub. L. 119–138; for the titles added on 2026-11-10, Pub. L. 119–138). There are 718 commits.

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
- **Tags.** The `edition-*` and `release-point-*` tags were made before title 26 was added and do not include it. Law
  tags (`law/<pl>`) for laws that also changed the earlier titles point at their earlier commits; tags for laws first
  seen in title 26 point at title 26 commits.

The blocks start at `17df0a7` (The 2017 edition of the US Code, title 17: §104A, §106A, §121A), `dea7531` (The 2017 edition of the US Code, title 26). `corpus.json` lists them under `end_blocks`.

The title 26 block's first commit gave the 2017 edition as printed. The commit after it, `b79490c` (`Kind:
correction`, `Corrects: dea7531…`, `In-force: 2018-01-12`), restates the text in force that day: 50 sections where Tax
Cuts and Jobs Act amendments (and three single changes by other laws) were already in force but not yet printed. Read
January 12, 2018 from it.

Titles 2, 5, 6, 7, 8, 10, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52 and 54 were added on 2026-11-10 as one more end block, `0a76bd9` (The 2017 edition of the US Code, titles 2, 5, 6, 7, 8, 10, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 54), built the same way: the text in force on January 12, 2018, then one commit for each law on each day its changes took effect. Read them per file, as above.

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
- **Everything before 2017.** The first commit is the 2017 edition as printed, without authors.
- **Retroactive dates.** A few changes took effect on a date before the law was enacted. Their commits carry the in-force date, so on dates in between the text shows words that had not yet been enacted. Each such commit says when the law was enacted.

Each commit links to the law's own words, and for anything that matters the law itself should be read.

## How it is built

The history is generated from the same data and the same code as the reader, so the text in this repository on any date is the text the reader shows for that date. The build script, the code it runs and the data it reads are in [`build/`](build/), byte for byte. The build is deterministic, and rebuilding from that data gives the same commits with the same hashes. [REPRODUCE.md](REPRODUCE.md) records the sources, every command, the software, the decisions made by hand and what an AI model did and did not do. Once other repositories refer to this one, updates are added as new commits instead of rewriting it.

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
