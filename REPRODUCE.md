# How this history was made, and how to make it again

This file records exactly how the repository was built: the sources, the commands, the software, the decisions made by hand, and what an AI model did and did not do. The script that made the history, the code it runs and the data it reads are in [`build/`](build/), byte for byte, so anyone with Node.js and git can rebuild it and check it.

## Short version

```sh
git clone https://github.com/lexifina/us-code-history && cd us-code-history/build
sha256sum -c DATA-SHA256SUMS                          # the data is the data this history was built from
npx jiti@2.6.1 scripts/us-code-git.ts ../../rebuilt   # rebuild the whole history into an empty folder
git -C ../../rebuilt log --format=%H                  # the same commits, with the same hashes
```

The last law commit is `7ada78137e229aa06314e11f361791197a8c3692`. A rebuild from `build/` reproduces it, and the 42 commits before it, hash for hash, on any day and in any time zone: every date in the history comes from the data, and the documentation commit is dated October 27, 2026, the day the data was built. `npx jiti scripts/us-code-git-check.ts ../../rebuilt` then checks every change against the text on the day it took effect.

## Sources

All legal text, and everything about each change, comes from official publishers of US law. Nothing was typed in, and no AI model wrote or edited any of it.

| What | Where | Documents | Retrieved |
| --- | --- | ---: | --- |
| Annual editions of each title, HTML | GovInfo, `https://www.govinfo.gov/content/pkg/USCODE-<year>-title<n>/html/USCODE-<year>-title<n>.htm` | 72 | October 26, 2026 |
| Release points since the last edition, each current through a named public law | Office of the Law Revision Counsel, `https://uscode.house.gov/download/releasepoints/us/pl/<congress>/<law>/htm_usc<n>@<congress>-<law>.zip` | 23 | October 26, 2026 |
| Each public law's text, with its amending instructions | GovInfo, `https://www.govinfo.gov/content/pkg/PLAW-<congress>publ<n>/uslm/PLAW-<congress>publ<n>.xml` | 33 | October 26, 2026 |
| Judicial Conference notices adjusting dollar amounts (11 U.S.C. §104) | the Federal Register, through GovInfo | 3 | with the editions |

Each document was requested once and cached, with a pause of a second between requests and the user agent `Mozilla/5.0 (compatible; Lexifina US Code history; +https://lexifina.com/watch)`. Retries after an error are not counted above. The data records each document's URL, its sha256 and when it was fetched. For each document the build also asked the Internet Archive's availability API (`https://archive.org/wayback/available`) for an archived copy, and records the answer.

The adjustment notices are used by the reader on lexifina.com, not by this history: the Code prints the amounts Congress enacted.

## The build, step by step

These commands made this repository, in order.

1. **The data.** For each title (1, 3, 4, 9, 11, 13, 17, 35, 39), Lexifina's backend ran `python -m services.us_code_history.build --title <n> --summaries`, with its defaults: the annual editions from 2017 to 2024, then every release point since. It ran in Lexifina's backend container, on Python 3.14.10. The code is in Lexifina's own repository at `src/backend/services/us_code_history` and is not published. It wrote one folder per title, built October 26, 2026 to October 27, 2026 (method version 1).
   - For each pair of consecutive versions, it finds the sections that changed and gathers the public laws enacted in between.
   - It carries out their amending instructions on the older text in date order, and compares the result with the newer version.
   - Each instruction becomes one change record: the provision before and after, the law, the dates, how far the replay matched, and the publisher's notes.
   - It reads each change's in-force date from the amending provision, an effective-date note, or the date of enactment.
2. **Copy into the site.** `node scripts/sync-us-code-history.mjs` copied the build into Lexifina's website at `app/watch/us-code/_data`. That folder is `build/app/watch/us-code/_data` here: 1040 files, listed with their sha256 in `build/DATA-SHA256SUMS`. The sha256 of that list is `e6e0a09fa65e4e5e145a7c2585bf0168dcd6fcce2cbb1497676ddf077039c60b`.
3. **This history.** From the website's folder, `npx jiti scripts/us-code-git.ts ../../us-code-history` wrote the 43 commits of the history, then one commit with the README, the licence, this file and `build/`.
4. **The check.** `npx jiti scripts/us-code-git-check.ts ../../us-code-history` compared every change record with the history.
   - The text after each change is in the file on the day it took effect, and the text before it was there the day before.
   - Where several instructions change one provision on the same day, only the last is checked against that day.
   - Every tagged version is compared with the printed text.
   - Run on 28 October 2026, all 274 checkable changes passed, after allowing for typography (the laws write "COVID-19" and "Pub. L. 105-277" with hyphens, the printed Code with en dashes). The tags matched the printed versions except where the README explains they differ.
5. **Publish.** `git push` to GitHub.

## Software

| Step | Software |
| --- | --- |
| The data (step 1) | Python 3.14.10 with httpx, in Lexifina's backend container |
| This history (steps 3 and 4) | Node.js 24.22.1, jiti 2.6.1 to run TypeScript, git 2.46.0, on Windows 11 |

The history build uses only Node's own modules and git. It makes no network requests.

The files under `build/`, with their git blob hashes:

| File | Git blob |
| --- | --- |
| `scripts/us-code-git.ts` | `b7026ab94cffd6f19204a6331f89a13f25bfc3d3` |
| `scripts/us-code-git-license.ts` | `8cbbfbf15f3ba11b42bdd1e6b8d1f46bad7f558c` |
| `scripts/us-code-git-reproduce.ts` | `5a4fd733fdf442b6d21d74aac6f933dd275cbcce` |
| `scripts/us-code-git-check.ts` | `ef82e44b3b5c7e3c26fd1cb98bd621c5541bb4ef` |
| `app/watch/us-code/_data/load.ts` | `184732668d3a0e7ac7f2970c5cc5cd2dbdb07c80` |
| `app/watch/us-code/_components/onDate.ts` | `66cd8ca857e9ca7f6dbedf54a50ba7752411882c` |
| `app/watch/us-code/_components/words.ts` | `599f19d17ca64e96d89af7fa4b5b6a7a1e51337a` |
| `app/tools/_engine/diff.ts` | `fddf92ce26606025b715aa27210219757e3e32dd` |

They are the same files as in Lexifina's website repository, at the same paths.

## How the text and the commits are derived

Everything below is done by `build/scripts/us-code-git.ts`, deterministically.

- **Text.** A section's text on a date is worked out by the same code as the reader on lexifina.com (`build/app/watch/us-code/_components/onDate.ts`):
  - It starts from the latest version printed by that date.
  - It undoes any change printed but not yet in force, and applies any change in force but not yet printed.
  - Where one printed version holds several changes to a provision, it replays them one at a time up to the first not yet in force.
- **Files.** There is one Markdown file per section, `title-<n>/<section>.md`. Each provision is on its own line, nested by its level. Text outside any numbered provision is a paragraph.
- **Commits.** There is one commit for each law on each day its changes took effect.
  - The author is the law, `Pub. L. <congress>-<number> (<short title>)`, at an address ending `.invalid`.
  - The author and committer dates are noon UTC on the day the changes took effect. The committer is `Lexifina <us-code-history@lexifina.com>`.
  - The message lists each change with its status, a one-sentence summary, the instruction and a link to the reader, then the trailers `Law:`, `Enacted:`, `In-force:`, `Printed-in:`, `Source:` and `Reader:`.
  - Text that changed in a newly printed version with no law taking effect that day goes in a commit of its own, named after that version.
- **Tags.** `edition-<year>` and `release-point-<congress>-<law>` mark the law in force on the day each printed version is current through.

## Decisions made by hand

These choices were made when the build was written, after looking at the data. They are in the code and can be changed there.

1. **Commits are dated the day a change took effect**, not the day it was enacted or printed. Noon UTC keeps the day the same in every time zone.
2. **A few changes took effect before their law was enacted.** Their commits keep the in-force date, and the commit says when the law was enacted.
3. **Dollar adjustments are not applied to the text.** The Code prints the dollar amounts Congress enacted, and the triennial adjustments appear in the Federal Register and in the Code's notes. The adjustment data also lists the whole chain of earlier notices under the 2022 notice, so applying it would give wrong amounts.
4. **A change that waits on a condition is left out of the text.** One change to 11 U.S.C. §1325 takes effect only when the Small Business Administration makes a determination.
5. **Replayed text is normalised to the printed Code's form.** Text rebuilt from a law's own words uses curly quotes, and these become straight quotes, as the printed Code has them. A space after a heading's dash is removed. Without this, a date between two printed versions would look like a change.
6. **Unexplained differences get their own commits.** Two printed versions read differently with no law taking effect that day: 17 U.S.C. §114, where a repeal note was added, and 11 U.S.C. §1325. Those differences are committed under the version's name. One known fault is there: in §1325, the change on a condition hides a sunset in force on 27 December 2022, so that change appears in the commit for the 2022 edition. The reader has the same fault.
7. **Section headings follow their own changes.** Ten headings were changed by law. Each takes effect with its law.
8. **The history stops on the day the data was built**, October 27, 2026. The documentation commit is dated that day too.

## What AI models did

**This repository** was built on 28 October 2026 in **Claude Code**, Anthropic's coding tool, by the model **Claude Opus 5.5** (model id `claude-opus-5-5`). It worked from a goal set by the user at Lexifina: to publish a git repository of the US Code history alongside the reader, applying the design argued for on lexifina.com. The model:

- wrote `build/scripts/us-code-git.ts`, `us-code-git-check.ts`, `us-code-git-license.ts` and `us-code-git-reproduce.ts`, the README, this file and the licence;
- moved the reader's text-on-a-date logic into `onDate.ts`, so the website and this history share it;
- ran the commands above and tested the result. That covered the check, a rebuild compared hash for hash, the README's commands in bash and PowerShell, GitHub's rendering, and the current text of two sections against Cornell's Legal Information Institute.

Testing found that every file was nested one level too shallow, and that was fixed before this file was written. The code that builds the data (step 1) and the reader were written earlier, in Claude Code sessions with the same model.

**The data** has one place where a language model wrote text: the one-sentence summary of each change, and of each law, in the commit messages.

- 347 of the 365 change summaries, and 37 of the 46 law summaries, were written when the data was built, by the backend's secondary model. On the build dates that was configured as OpenAI's `gpt-5.4-mini`, with `gpt-5.4-nano` as a fallback. The data does not record which of the two answered each request.
- Each summary was checked by code before it was kept. Every number, dollar amount and quotation in it had to appear in the change's before or after text or in the law's instruction, and every change it cites had to exist.
- A summary that failed was replaced by a sentence written by a rule from the replayed operations. The rest of the summaries were written that way.
- The data marks each summary's source: `model, checked` or `rule`.

No model wrote or edited any legal text. Every word of every section is copied by code from GovInfo and the Law Revision Counsel. Every date, every law and every status comes from the publishers' text or from the replay of a law's own instructions. No model is called when this history is built or checked, and rebuilding it needs no model and gives the same result.

The user decided what was in scope and whether the repository is public. The work has not been reviewed line by line by a lawyer. As the README says, for anything that matters the law itself should be read.

## Changes to this history after it was published

- **28 October 2026.**
  - The repository was published under `alan-yahya`, then made private on the user's instruction, then moved to the `lexifina` organisation.
  - It was rebuilt once that day to fix the nesting of provisions, which changed every commit hash.
  - Lexifina's global-law repository refers to it, so this file and `build/` were then added in a commit of their own, keeping the published commits' hashes. A full rebuild puts them in the documentation commit instead.
- **10 November 2026.** The record before 2017 was put in front of the history (owner's decision), which changed every
  commit hash and left every text unchanged; see "History before 2017" below. Hashes named in this file before that
  section are the earlier ones: `build/history-2026-11-10/old-to-new.tsv` maps them, and the earlier history is the
  branch `archive/main-before-history-2026-11-10`.
- **11 November 2026.** Rewritten once more to correct the record before 2017 and put back the paragraphs the first
  build dropped (see "Corrections of 2026-11-11" below); `build/history-2026-11-11/old-to-new.tsv` maps the earlier
  commits; the previous main is the branch `archive/main-before-rewrite2-2026-11-11`.

## End blocks added on 2026-11-09: title 26 and three sections of title 17

These commits were added after the documentation commits above, without rewriting anything. They are not rebuilt by
the short version above, which makes the nine-title history only.

- **Code.** The data was built with a copy of Lexifina's `services/us_code_history` with four general fixes (CHANGES.md,
  2026-11-09), on the host with Python 3.12.10 (lxml, httpx), not the backend container:
  `python -X utf8 -m services.us_code_history.build --title 26 --out out-new` and the same for title 17. No `--summaries`:
  **no AI model ran at data-build time for these blocks**; every summary in their commit messages is written by rule
  from the record. Titles 9, 11 and 17 were rebuilt with the same code and compared record for record with a build
  from the unchanged code: 7/7, 122/122 and 108/108 identical, plus the new §121A record.
- **Sources** as above (GovInfo editions and public laws, OLRC release points), 44 public laws for title 26,
  fetched 2026-10-28 to 2026-11-09, one request at a time with a
  second between requests. robots.txt of govinfo.gov and uscode.house.gov was read; neither disallows these paths.
- **Commits.** `scripts/us-code-git-append.ts`, a copy of `us-code-git.ts` that writes onto the clone's HEAD as
  `refs/heads/append` instead of a new repository, leaves out the reader links (the reader does not show title 26 yet)
  and adds only law tags that do not exist yet; `--missing-sections` adds only the files absent at HEAD (title 17).
  Each block was checked with global-law's `check_corpus.py` against global-law's pin and pushed as a fast-forward.
- **Replay.** Title 26: 1757 of 3075 change records reproduced the next printed version exactly. The rest are
  committed as partly confirmed, publisher's note only, or "Printed text differs" under the printed version's name.
- **AI.** These blocks were made by Claude Code (Claude Opus 5.5, `claude-opus-5-5`): it wrote the fixes, the append
  script and this documentation, and ran the commands. No AI model wrote or edited legal text or chose a date.

### The end blocks, step by step

Everything named here is in [`build/end-blocks-2026-11-09/`](build/end-blocks-2026-11-09/). The data (the title 26 and
title 17 folders the build wrote, 2,089 files) is the release asset `end-blocks-data-2026-11-09.tar.gz` (sha256 in
`ARCHIVE-SHA256`; each file's sha256 in `DATA-SHA256SUMS`).

1. **Data.** `pipeline-fixes.patch` applied to Lexifina's `services/us_code_history`, then
   `python -X utf8 -m services.us_code_history.build --title 26 --out <out>` (and `--title 17`), with Python 3.12.10.
   Before and after the patch, titles 9, 11 and 17 were built and compared record for record: 7/7, 122/122 and
   108/108 identical, plus the one new §121A record.
2. **Title 17 block.** From a clone at `770df0a`: `npx jiti scripts/us-code-git-append.ts <clone> --missing-sections`
   with only title 17's data staged under `app/watch/us-code/_data`: commits `17df0a7` and `437c743`.
3. **Title 26 block.** From a clone at `437c743`: `npx jiti scripts/us-code-git-append.ts <clone>` with only title 26's
   data staged. The first commit was pushed (`dea7531`) before a later data build, which also tries large laws
   enacted just before the 2017 edition's cutoff, changed the starting text of 50 sections. So the regenerated block
   was put onto `dea7531` with `reparent.py`: a correction commit `b79490c` (message `fix-msg.txt`, file list added by
   `fix_msg.py`) whose tree is the regenerated first commit's, then every later commit re-created with the same tree,
   author, committer, dates and message. `retag.py` moved the 71 new law tags onto those commits. The text at the tip
   is identical to the regenerated block's.
4. **Checks.** `check_corpus.py` passed before each push (`437c743`, `dea7531`, `6b4dfef`, `9ba697c`, `cd31a9f`).
   `RANGE=437c743..<tip> npx jiti scripts/us-code-git-check-block.ts <clone>` (the history check read within the
   block): of 1,810 changes checkable on their in-force day, 1,588 have the new words in the file that day and not the
   old ones; most of the rest are partly confirmed changes, and some are the Code's "[Repealed …]" placeholders, which
   the files leave out.

## End block added on 2026-11-10: titles 2, 5, 6, 7, 8, 10, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30, 31, 32, 33, 34, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52 and 54

Added after the documentation commits above, without rewriting anything, exactly as the title 26 block of 9 November.

- **Code.** The same copy of `services/us_code_history` as title 26 (with its four general fixes), on the host with
  Python 3.12.10: `python -X utf8 -m services.us_code_history.build --title N --out out-all` for each title. No
  `--summaries`: no AI model ran at data-build time; every summary in these commit messages is written by rule.
- **Sources** as above (GovInfo editions and public laws, OLRC release points), one request at a time per lane with a
  second between requests; most files came from the cache of the earlier builds.
- **Commits.** `scripts/us-code-git-append.ts` onto the published head, as one block starting at `0a76bd9`;
  only law tags that did not exist yet were added. Checked with `us-code-git-check-block.ts` and global-law's
  `check_corpus.py`, pushed as a fast-forward.
- **Replay.** 15279 of 60544 change records reproduced the next printed version exactly. Per title:
  - title 2 (The Congress): 1548 sections, 718 records, 169 replayed
  - title 5 (Government Organization and Employees): 1127 sections, 1182 records, 252 replayed
  - title 6 (Domestic Security): 586 sections, 1270 records, 233 replayed
  - title 7 (Agriculture): 2841 sections, 2465 records, 870 replayed
  - title 8 (Aliens and Nationality): 332 sections, 217 records, 46 replayed
  - title 10 (Armed Forces): 4417 sections, 14510 records, 3307 replayed
  - title 12 (Banks and Banking): 1913 sections, 854 records, 190 replayed
  - title 14 (Coast Guard): 759 sections, 2516 records, 224 replayed
  - title 15 (Commerce and Trade): 2634 sections, 2149 records, 359 replayed
  - title 16 (Conservation): 5033 sections, 3001 records, 522 replayed
  - title 18 (Crimes and Criminal Procedure): 1330 sections, 529 records, 346 replayed
  - title 19 (Customs Duties): 1054 sections, 912 records, 88 replayed
  - title 20 (Education): 1762 sections, 1047 records, 234 replayed
  - title 21 (Food and Drugs): 718 sections, 1162 records, 223 replayed
  - title 22 (Foreign Relations and Intercourse): 3309 sections, 2700 records, 461 replayed
  - title 23 (Highways): 153 sections, 676 records, 474 replayed
  - title 24 (Hospitals and Asylums): 122 sections, 30 records, 10 replayed
  - title 25 (Indians): 2366 sections, 562 records, 101 replayed
  - title 27 (Intoxicating Liquors): 29 sections, 0 records, 0 replayed
  - title 28 (Judiciary and Judicial Procedure): 766 sections, 90 records, 54 replayed
  - title 29 (Labor): 766 sections, 346 records, 25 replayed
  - title 30 (Mineral Lands and Mining): 640 sections, 257 records, 26 replayed
  - title 31 (Money and Finance): 492 sections, 295 records, 197 replayed
  - title 32 (National Guard): 73 sections, 31 records, 19 replayed
  - title 33 (Navigation and Navigable Waters): 1530 sections, 2271 records, 599 replayed
  - title 34 (Crime Control and Law Enforcement): 802 sections, 1584 records, 608 replayed
  - title 36 (Patriotic and National Observances, Ceremonies, and Organizations): 1172 sections, 281 records, 121 replayed
  - title 37 (Pay and Allowances of the Uniformed Services): 214 sections, 581 records, 201 replayed
  - title 38 (Veterans' Benefits): 1155 sections, 1690 records, 661 replayed
  - title 40 (Public Buildings, Property, and Works): 452 sections, 181 records, 114 replayed
  - title 41 (Public Contracts): 241 sections, 169 records, 68 replayed
  - title 42 (The Public Health and Welfare): 8131 sections, 8466 records, 1746 replayed
  - title 43 (Public Lands): 1349 sections, 456 records, 29 replayed
  - title 44 (Public Printing and Documents): 349 sections, 101 records, 75 replayed
  - title 45 (Railroads): 258 sections, 64 records, 9 replayed
  - title 46 (Shipping): 1036 sections, 1403 records, 690 replayed
  - title 47 (Telecommunications): 428 sections, 491 records, 36 replayed
  - title 48 (Territories and Insular Possessions): 515 sections, 132 records, 16 replayed
  - title 49 (Transportation): 1335 sections, 2276 records, 1324 replayed
  - title 50 (War and National Defense): 1372 sections, 2671 records, 465 replayed
  - title 51 (National and Commercial Space Programs): 247 sections, 87 records, 27 replayed
  - title 52 (Voting and Elections): 171 sections, 22 records, 9 replayed
  - title 54 (National Park Service and Related Programs): 366 sections, 99 records, 51 replayed

## History before 2017, added on 2026-11-10

Built in a separate working folder and published first as the branch `history-full`, then made `main` (the owner's
decision, 10 November 2026). The code is in `build/history-2026-11-10/tools/`, byte for byte.

- **Sources.** GovInfo's annual editions, `https://www.govinfo.gov/content/pkg/USCODE-<year>-title<n>/html/USCODE-<year>-title<n>.htm`,
  for 1994 to 2017, retrieved November 10, 2026, one request at a time per lane (three lanes) with 1.5 s between
  requests, user agent as above. `build/history-2026-11-10/editions.tsv` lists every edition used with its sha256, size
  and cutoff, and the 95 title-years GovInfo does not publish. Law names and dates: the section source credits, else
  GovInfo's MODS records (`https://www.govinfo.gov/metadata/pkg/PLAW-<c>publ<n>/mods.xml`, 104th Congress on), kept in
  `laws.json`. The Office of the Law Revision Counsel's prior release points page answered 404 (asked once).
- **Parsing.** `tools/fetch_parse.py`, with the same `services/us_code_history` as title 26 plus one change: a paragraph
  may carry attributes after its class (from the 2012 edition on, GovInfo adds `style`). It also keeps each edition's
  bracketed notices for repealed and moved sections. Raw files were parsed and deleted; the parse is gzipped JSON.
- **Rendering.** `tools/render.py` writes each section as the generator does: titles 1, 3, 4, 9, 11, 13, 17 (except
  §104A, §106A, §121A), 35 and 39 as the first generator (list depth from the printed level, no escaping), the others as
  the later one. The 2017 edition rendered this way equals the files of the 2017 edition commits except where those
  commits already applied later laws or skip `style` paragraphs.
- **Commits.** `tools/build_block.py <title>` (rules in its docstring and in the README) writes one block per title and
  checks that it ends at exactly the files the 2017 edition commits of this history give;
  `tools/assemble.py 26 1 2 ... 54` writes the blocks, title 26 first, then replays every commit of the earlier history
  with the same author, committer, dates, message and file blobs, through `git fast-import`, and checks that the final
  tree equals the earlier history's. `tools/run_all.py` ran both; `tools/blame_stats.py` measures who `git blame` credits.
- **Checks.** Final tree `27abda9446124ae1b831272a50bccf18ebcf11d1` before and after. A sample of 150 title 26 files: the
  lines `git blame` credited to the 2017 edition fell from 90.5% to 0.3%; 36% now name a law enacted before 2018.
- **No AI model** wrote any text or message; an AI coding agent wrote and ran the scripts.

| Title | Commits | Section changes credited to a law | to an edition | in part | Files where the 2017 text lacks `style` paragraphs |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 7 | 9 | 1 | 0 | 0 |
| 2 | 152 | 892 | 1358 | 5 | 6 |
| 3 | 12 | 37 | 1 | 0 | 0 |
| 4 | 16 | 31 | 1 | 0 | 1 |
| 5 | 235 | 1018 | 156 | 19 | 10 |
| 6 | 74 | 599 | 108 | 0 | 0 |
| 7 | 130 | 2134 | 1156 | 28 | 7 |
| 8 | 133 | 394 | 207 | 18 | 14 |
| 9 | 3 | 1 | 11 | 0 | 0 |
| 10 | 164 | 5474 | 527 | 71 | 63 |
| 11 | 32 | 248 | 7 | 0 | 1 |
| 12 | 155 | 1191 | 651 | 4 | 35 |
| 13 | 11 | 12 | 0 | 0 | 0 |
| 14 | 44 | 341 | 45 | 5 | 0 |
| 15 | 319 | 1871 | 836 | 22 | 22 |
| 16 | 325 | 2355 | 1715 | 15 | 7 |
| 17 | 44 | 208 | 10 | 6 | 4 |
| 18 | 233 | 1208 | 80 | 7 | 6 |
| 19 | 113 | 717 | 331 | 4 | 31 |
| 20 | 233 | 2768 | 2124 | 10 | 15 |
| 21 | 126 | 754 | 285 | 11 | 18 |
| 22 | 239 | 1814 | 868 | 6 | 9 |
| 23 | 57 | 478 | 35 | 0 | 0 |
| 24 | 27 | 65 | 24 | 0 | 0 |
| 25 | 127 | 679 | 1752 | 3 | 6 |
| 26 | 236 | 3557 | 456 | 133 | 301 |
| 27 | 7 | 3 | 7 | 0 | 0 |
| 28 | 130 | 380 | 196 | 1 | 2 |
| 29 | 143 | 748 | 658 | 15 | 22 |
| 30 | 57 | 145 | 158 | 0 | 0 |
| 31 | 162 | 398 | 12 | 2 | 3 |
| 32 | 25 | 90 | 3 | 0 | 0 |
| 33 | 130 | 856 | 363 | 3 | 5 |
| 34 | 35 | 186 | 524 | 2 | 6 |
| 35 | 42 | 228 | 74 | 3 | 2 |
| 36 | 62 | 1312 | 1350 | 4 | 0 |
| 37 | 50 | 993 | 54 | 1 | 0 |
| 38 | 161 | 1788 | 74 | 5 | 1 |
| 39 | 45 | 137 | 11 | 0 | 0 |
| 40 | 112 | 694 | 667 | 4 | 0 |
| 41 | 60 | 375 | 238 | 0 | 0 |
| 42 | 708 | 7315 | 4398 | 73 | 125 |
| 43 | 93 | 257 | 309 | 1 | 0 |
| 44 | 53 | 316 | 9 | 1 | 1 |
| 45 | 43 | 82 | 62 | 1 | 1 |
| 46 | 73 | 978 | 62 | 10 | 4 |
| 47 | 76 | 261 | 176 | 1 | 4 |
| 48 | 57 | 146 | 50 | 3 | 1 |
| 49 | 194 | 2060 | 259 | 17 | 13 |
| 50 | 111 | 1064 | 845 | 8 | 3 |
| 51 | 9 | 47 | 0 | 0 | 0 |
| 52 | 1 | 0 | 0 | 0 | 0 |
| 54 | 7 | 36 | 2 | 0 | 0 |

## Corrections of 2026-11-11, and title 26 from 1986

The code is in `build/history-2026-11-11/tools/`, byte for byte (it supersedes `build/history-2026-11-10/tools/`).

- **Dropped paragraphs.** `tools/restore_data.py` parses every printed version the history from 2017 uses (the 2017 to
  2024 editions from GovInfo, the release points from the Office of the Law Revision Counsel, all from the cache of the
  earlier builds) with the parser the first build used and with the corrected one, renders both, and keeps each run of
  lines the corrected one adds, with up to three lines of context on each side; every difference was a pure addition.
  `tools/restore.py` puts each run into a file's text as of a date, using the printed version current that day.
  `tools/assemble.py` applies it to the 2017 starting text the blocks end at and to every file version in the replayed
  commits from 2017 (1,575; 16 runs skipped for want of a unique place), and checks that the final tree differs from the
  previous main's only by added lines in those files: 667 files, 1,258 lines added, none removed.
- **Moved sections.** `build_block.py`: a section new to a title whose notes say it was formerly classified elsewhere
  (or transferred, or editorially reclassified) is credited to the edition. Title 34 is not built before 2017.
- **Title 26 from 1986.** `tools/reverse1986.py` reverses, for each section of the 1994 edition, the amendment-note
  entries of laws enacted after October 22, 1986, newest law first, each only where its words name exactly one place;
  `build_block.py 26 --from1986` writes the 1986 starting commit and one commit per law for the sections where every
  entry reversed, and the 1994 edition commit starts the rest. `tools/crosscheck_stat.py` checked a random sample of 30
  reversed "substituted X for Y" entries against the amending laws in GovInfo's STATUTE collection (granule PDFs, read
  with pdftotext): 14 confirmed (12 by text search, 2 on reading), 10 not verifiable by text search (OCR of the scanned
  volumes; notes that paraphrase the instruction), 6 not checked (the law's pages could not be located), 0
  contradicted (`crosscheck-stat.json`).
- **Run.** `tools/build_many.py` in eight parallel lanes, then `tools/assemble.py 26 1 2 ... 54` (without 34).

| Title | Commits | Section changes credited to a law | to an edition | in part |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 7 | 9 | 1 | 0 |
| 2 | 151 | 892 | 1355 | 4 |
| 3 | 12 | 37 | 1 | 0 |
| 4 | 15 | 31 | 0 | 0 |
| 5 | 235 | 1019 | 150 | 18 |
| 6 | 76 | 595 | 112 | 0 |
| 7 | 130 | 2131 | 1153 | 28 |
| 8 | 133 | 394 | 193 | 18 |
| 9 | 3 | 1 | 11 | 0 |
| 10 | 164 | 5468 | 531 | 71 |
| 11 | 31 | 248 | 6 | 0 |
| 12 | 155 | 1191 | 616 | 4 |
| 13 | 11 | 12 | 0 | 0 |
| 14 | 44 | 341 | 45 | 5 |
| 15 | 320 | 1871 | 816 | 22 |
| 16 | 325 | 2355 | 1708 | 15 |
| 17 | 43 | 208 | 6 | 6 |
| 18 | 232 | 1208 | 74 | 7 |
| 19 | 113 | 717 | 300 | 4 |
| 20 | 233 | 2724 | 2155 | 10 |
| 21 | 125 | 758 | 278 | 5 |
| 22 | 239 | 1812 | 862 | 6 |
| 23 | 57 | 478 | 35 | 0 |
| 24 | 27 | 65 | 24 | 0 |
| 25 | 126 | 676 | 1749 | 3 |
| 26 | 259 | 3661 | 292 | 29 |
| 27 | 7 | 3 | 7 | 0 |
| 28 | 131 | 379 | 195 | 1 |
| 29 | 143 | 747 | 639 | 15 |
| 30 | 57 | 145 | 158 | 0 |
| 31 | 161 | 398 | 9 | 2 |
| 32 | 25 | 90 | 3 | 0 |
| 33 | 130 | 857 | 360 | 2 |
| 35 | 41 | 228 | 72 | 3 |
| 36 | 62 | 1312 | 1350 | 4 |
| 37 | 50 | 993 | 54 | 1 |
| 38 | 161 | 1788 | 74 | 5 |
| 39 | 45 | 137 | 11 | 0 |
| 40 | 112 | 694 | 667 | 4 |
| 41 | 60 | 375 | 238 | 0 |
| 42 | 707 | 7286 | 4333 | 72 |
| 43 | 93 | 256 | 310 | 1 |
| 44 | 53 | 316 | 9 | 1 |
| 45 | 42 | 82 | 61 | 1 |
| 46 | 73 | 972 | 67 | 10 |
| 47 | 75 | 261 | 172 | 1 |
| 48 | 57 | 146 | 50 | 3 |
| 49 | 194 | 2060 | 255 | 16 |
| 50 | 105 | 1006 | 901 | 8 |
| 51 | 9 | 47 | 0 | 0 |
| 52 | 1 | 0 | 0 | 0 |
| 54 | 7 | 36 | 2 | 0 |
