# Git for the US Code

The text of nine titles of the United States Code, with a commit for each law on each day its changes to them took effect, since the 2017 edition. **Each commit is a law taking effect.** Its author is the public law that made the change, and its date is the day the change came into force.

So the questions a lawyer asks of a statute become git commands:

| The question | The command |
| --- | --- |
| What did §1182 say on 1 May 2022? | `git show $(git rev-list -1 --before=2022-05-02 main):title-11/1182.md` |
| Which law wrote each provision? | `git blame title-11/1182.md` |
| What changed between two dates? | `git diff $(git rev-list -1 --before=2020-01-01 main) $(git rev-list -1 --before=2023-01-01 main) -- title-11/1182.md` |
| Everything one law changed | `git log -p --author="Pub. L. 116-136"` |
| Every change to a section | `git log -p -- title-11/1182.md` |
| The Code as a printed version stood | `git checkout edition-2022` or `git checkout release-point-119-73` |

If you would rather not use a terminal, the same history has a reader at **[lexifina.com/watch/us-code](https://lexifina.com/watch/us-code)**: pick a date and read the text in force on it, see the Act behind each phrase in colour, and see what else in the title relies on a provision. For example, [11 U.S.C. §1182](https://lexifina.com/watch/us-code/title-11/1182).

## What is here

| Title | Name | Sections | Changes | Reader |
| --- | --- | ---: | ---: | --- |
| [Title 1](title-1/) | General Provisions | 39 | 7 | [Read it](https://lexifina.com/watch/us-code/title-1) |
| [Title 3](title-3/) | The President | 60 | 44 | [Read it](https://lexifina.com/watch/us-code/title-3) |
| [Title 4](title-4/) | Flag and Seal, Seat of Government, and the States | 47 | 8 | [Read it](https://lexifina.com/watch/us-code/title-4) |
| [Title 9](title-9/) | Arbitration | 33 | 7 | [Read it](https://lexifina.com/watch/us-code/title-9) |
| [Title 11](title-11/) | Bankruptcy | 278 | 122 | [Read it](https://lexifina.com/watch/us-code/title-11) |
| [Title 13](title-13/) | Census | 65 | 1 | [Read it](https://lexifina.com/watch/us-code/title-13) |
| [Title 17](title-17/) | Copyrights | 147 | 108 | [Read it](https://lexifina.com/watch/us-code/title-17) |
| [Title 35](title-35/) | Patents | 168 | 12 | [Read it](https://lexifina.com/watch/us-code/title-35) |
| [Title 39](title-39/) | Postal Service | 175 | 56 | [Read it](https://lexifina.com/watch/us-code/title-39) |

Each section is one Markdown file, `title-<n>/<section>.md`, with one provision per line, so `git blame` names a law for every paragraph, subparagraph and clause. The history covers the annual editions from 2017 to 2024 and the release points since, up to Pub. L. 119–134. There are 44 commits.

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

Each commit links to the law's own words, and for anything that matters the law itself should be read.

## How it is built

The history is generated from the same data and the same code as the reader, so the text in this repository on any date is the text the reader shows for that date. The build is deterministic, and rebuilding from the same data gives the same commits. It is regenerated when the data is updated, so the history may be rewritten.

Built by [Lexifina](https://lexifina.com). For corrections, open an issue.

## License

The text of the US Code is a work of the United States Government and is in the public domain. The history, commit messages and README are released under [CC BY 4.0](LICENSE.md).
