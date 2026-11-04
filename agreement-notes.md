# Step 5 reading notes — parser-facing

Two agreements read end to end (reps & warranties skimmed; consideration, no-shop/go-shop,
efforts, conditions, termination read closely). Every format below was quoted from the
actual EDGAR exhibit text, not approximated.

Sources:
- juniper-hpe-2024: https://www.sec.gov/Archives/edgar/data/1043604/000119312524005659/d107225dex21.htm (Ex. 2.1 to 8-K, accession 0001193125-24-005659)
- dun-bradstreet-clearlake-2025: https://www.sec.gov/Archives/edgar/data/1799208/000110465925027293/tm2510133d1_ex2-1.htm (Ex. 2.1 to 8-K, accession 0001104659-25-027293)

---

## Agreement 1: HPE / Juniper (strategic, all-cash, regulatory risk)

Document: "AGREEMENT AND PLAN OF MERGER" dated as of January 9, 2024, among Juniper
Networks, Inc. ("Company"), Hewlett Packard Enterprise Company ("Parent") and Jasmine
Acquisition Sub, Inc. ("Merger Subsidiary"). One-step DGCL 251 merger. No "EXECUTION
VERSION" legend.

### Heading formats (regex unit tests)
- Articles: arabic numerals, all caps, number and title on separate lines:
      ARTICLE 10
      TERMINATION
- Sections: the word "Section", two-digit zero-padded number, trailing period, then the
  title and a final period:
      Section 10.01.
      Termination.
  Numbering runs Section 1.01 through Section 11.14 (11 articles).
- Subsections: "(a)", "(b)"; sub-clauses "(i)", "(ii)". In-text references look like
  "Section 2.02(b)" and "Article 9".

### Where definitions live
Article 1 does the work, in two parts:
1. Section 1.01 "Definitions" — one long alphabetical list ("Acquisition Proposal",
   "Affiliate", ...).
2. Terms defined inside operative sections are indexed in a two-column Term/Section
   table at the end of Section 1.01, e.g. "Company Termination Fee -> 11.04(b)(i)",
   "End Date -> 10.01(b)(i)". A parser must merge both, or it will miss the
   termination fees entirely (they are NOT in the alphabetical list).
Section 1.02 "Other Definitional and Interpretative Provisions" is interpretive rules
only (hereof/herein, "including" without limitation, etc.).

### Where the table of contents ends
TOC starts with "TABLE OF CONTENTS" right after the title block and runs pages i-iii,
ending at the line "iii". The body restarts with a second "AGREEMENT AND PLAN OF MERGER"
heading followed by the preamble "AGREEMENT AND PLAN OF MERGER (this "Agreement"), dated
as of January 9, 2024...". Strip rule: delete everything before the second occurrence of
"AGREEMENT AND PLAN OF MERGER".

### Cross-references (retrieval weakness)
~327 "Section X.YZ" references in the body; 126 of them carry a subsection letter
("Section 2.02(b)", "Section 9.01(c)"); ~35 "Article N" references.
Worst trap found: the termination article (Article 10) says nothing about money. The fee
amounts and triggers live two articles away in Section 11.04 ("Expenses"), so the chunk
that matches "what happens if the deal is terminated" just points onward. Same for
"End Date" — defined mid-sentence inside the termination trigger Section 10.01(b)(i),
not in Article 1.

### Key substantive reads
- Consideration: Section 2.02(a) — $40.00 per Share in cash, without interest
  ("Merger Consideration"). Fixed price, no collar.
- No-shop: Section 6.03 "No Solicitation; Other Offers" — straight no-shop (no go-shop),
  with fiduciary exception; Superior Proposal termination right in Section 10.01(d)(i).
- Efforts: Section 8.01 — "reasonable best efforts" to get Required Regulatory Approvals,
  expressly including "Remedy Actions" (sale/divestiture/license of businesses, hold
  separates, behavioral relief, defending litigation through appeal), capped by a carve-out
  for actions with a material adverse effect measured relative to the size of the Company
  (the combined-company test at Juniper's scale).
- Conditions: Article 9 — Section 9.01: no injunction/illegality; Company Stockholder
  Approval; HSR waiting period expiry + other Required Regulatory Approvals obtained
  "without the imposition ... of a Burdensome Condition". No financing condition.
- Termination: Section 10.01 — End Date January 9, 2025, auto-extending to April 9, 2025,
  then July 9, 2025, then October 9, 2025 if only the regulatory conditions (9.01(c) /
  9.01(a) as it relates to 9.01(c)) are unsatisfied.
- Fees: Section 11.04(b) Company Termination Fee $407,500,000; Section 11.04(c) Parent
  Termination Fee $815,000,000, triggered by termination on End Date / final injunction
  where only the regulatory conditions failed, or by Company termination for Parent's
  material breach of Section 8.01. Both fees are liquidated damages / sole remedy
  (subject to intentional fraud).
- Financing (strategic-deal version): Section 5.08 — Parent delivered a Debt Commitment
  Letter (Citigroup, JPMorgan, Mizuho) with redacted fee letters; Section 6.05 Financing
  Assistance covenant on the Company; Section 11.14 "Financing Provisions" (no-recourse
  to Financing Sources). No equity commitment letter, no limited guarantee, no marketing
  period, and Parent's closing obligation is not conditioned on the debt.
- Governing law: Section 11.07 — Delaware; Section 11.08 — Delaware Chancery.

---

## Agreement 2: Dun & Bradstreet / Clearlake (PE take-private, go-shop)

Document: "EXECUTION VERSION" legend, "AGREEMENT AND PLAN OF MERGER" dated as of
March 23, 2025, among Dun & Bradstreet Holdings, Inc. ("Company"), Denali Intermediate
Holdings, Inc. ("Parent") and Denali Buyer, Inc. ("Merger Sub"). One-step DGCL merger;
Voting Agreements signed concurrently (recitals).

### Heading formats (regex unit tests)
- Articles: ROMAN numerals, all caps, number and title on separate lines (title can wrap):
      ARTICLE VIII
      TERMINATION
  and
      ARTICLE II
      ORGANIZATIONAL DOCUMENTS, DIRECTORS AND OFFICERS
      OF THE SURVIVING CORPORATION
- Sections: bare number, one digit each side, NO "Section" prefix, no zero padding; the
  title follows and ends with a period:
      8.2
      Termination
      by Either Parent or the Company
      .
  Numbering runs 1.1 through 9.15 (9 articles).
- Subsections: "(a)", "(b)"; sub-clauses "(i)", "(ii)". In-text references look like
  "Section 8.3(b)" and "ARTICLE II"; plural form "Sections 7.1 and 7.2" also occurs.
- Quirk: termination sections carry parenthetical topic labels used as shorthand
  elsewhere: "Section 8.3(b) (Termination for Superior Proposal)", "Section 8.2(a)
  (Termination Date)", "Section 8.3(c) (Failure to Close)". Section 8.5 refers back to
  triggers by these labels.

### Where definitions live
Hybrid, and different from HPE/Juniper:
1. Section 9.15 "Definitions" — the alphabetical catch-all near the END of the document
   (starts "For purposes of this Agreement, the following terms, when used herein, shall
   have the respective meanings set forth below"). Most defined terms resolve here,
   including "Acquisition Proposal", "Superior Proposal", "Excluded Party".
2. Operative sections still define terms inline ("Merger Consideration" in 3.1(a)(i),
   "Go-Shop Period" and "No-Shop Period Start Date" in 6.2(a)(i)).
3. A front INDEX OF DEFINED TERMS (pages iv-vii, between the TOC and the body) maps every
   defined term to its section. It sits in the FRONT matter, so the TOC-strip must remove
   it too, but it is also a ready-made definition index if you keep it as metadata.

### Where the table of contents ends
"TABLE OF CONTENTS" runs pages i-iii (with "TABLE OF CONTENTS (cont.)" headers) and ends
at the line "iii". The INDEX OF DEFINED TERMS follows (pages iv-vii), ending at "vii".
The body starts with a second "AGREEMENT AND PLAN OF MERGER" followed by "This AGREEMENT
AND PLAN OF MERGER (this "Agreement"), is entered into as of March 23, 2025...".
Strip rule: delete everything before the second occurrence of "AGREEMENT AND PLAN OF
MERGER" — same rule as HPE/Juniper, but the dropped region is larger (TOC + index).

### Cross-references (retrieval weakness)
~258 "Section X.Y" references in the body; 134 carry a subsection letter
("Section 8.5(b)", "Section 6.2(a)"); ~44 "ARTICLE X" references.
Worst trap: the fee economics in Section 8.5 are expressed almost entirely through
cross-references — the Go-Shop Termination Fee trigger reads "if the Company terminates
... pursuant to Section 8.3(b) (Termination for Superior Proposal) during the Go-Shop
Period or ... with an Excluded Party", which sends you to three other chunks (8.3(b),
6.2(a)(i) for Go-Shop Period, and the Excluded Party definition) before the answer
resolves. The index-of-defined-terms style also means many definitional answers point
from the index to a section.

### Key substantive reads
- Consideration: Section 3.1(a)(i) — $9.15 per Share in cash, without interest
  ("Merger Consideration"); appraisal rights for Dissenting Stockholders (Section 3.3).
- Go-shop: Section 6.2(a)(i) — 30-day Go-Shop Period from signing until 11:59 p.m.
  Eastern on the "No-Shop Period Start Date"; Company may solicit, negotiate and share
  non-public information under an Acceptable Confidentiality Agreement (24-hour
  notice/sharing obligations to Parent). "Excluded Party" mechanic lets go-shop bidders
  keep talking after the period ends.
- Efforts: Section 6.5 — mutual "reasonable best efforts"; HSR filing within 20 Business
  Days. Regulatory load is light relative to HPE/Juniper (no Remedy Actions covenant).
- Conditions: Article VII — Section 7.1: Company Requisite Vote, HSR expiry + consents
  listed on a disclosure-letter schedule, no legal restraint; 7.2/7.3 bring-downs and
  covenant compliance; 7.4 frustration of conditions. NO financing condition — instead
  Section 1.2 gates Closing on the end of the "Marketing Period" for the debt financing.
- Termination: Article VIII — Termination Date December 23, 2025 (8.2(a)); Company may
  terminate for Superior Proposal (8.3(b)) or for Parent's Failure to Close after a
  3-Business-Day cure window once all conditions are met (8.3(c)).
- Fees: Section 8.5(b) — Company Termination Fee $123,000,000, cut in half to the
  $61,500,000 "Go-Shop Termination Fee" if the Company terminates during the Go-Shop
  Period or signs with an Excluded Party; 8.5(c) 12-month tail; 8.5(d) — Parent
  Termination Fee $266,400,000 on Parent breach or Failure to Close.
- Financing (PE version): Section 5.7 — Debt Commitment Letter (redacted economics) plus
  an Equity Commitment Letter from six Clearlake funds ("Equity Investors") committing
  the full cash equity; the Company is an EXPRESS THIRD PARTY BENEFICIARY of the Equity
  Commitment Letter. A Limited Guarantee from the same funds guarantees the Parent
  Termination Fee, Parent's expense obligations (6.10(a)) and financing indemnity
  (6.19(g)), subject to a "Reimbursement and Enforcement Cap". Section 6.19 is the
  financing covenant (efforts to consummate financing, substitute financing, Marketing
  Period mechanics); Section 5.8 Solvency rep; Section 9.14 No Recourse.
- Governing law: Section 9.5(a) — Delaware; Section 9.5(b) — Delaware Chancery;
  heading is all-caps "Governing Law and Venue; Waiver of Jury Trial".

---

## Structural differences that matter for extraction

| Feature | HPE/Juniper (strategic) | D&B/Clearlake (PE) |
|---|---|---|
| Articles numbered | arabic ("ARTICLE 10") | roman ("ARTICLE VIII") |
| Section labels | "Section 10.01." (zero-padded, "Section" prefix) | "8.2" (bare, no prefix) |
| Definitions | Article 1 list + term/section index table | Section 9.15 catch-all + front INDEX OF DEFINED TERMS |
| Articles count | 11 | 9 |
| Shop mechanics | no-shop only (6.03) | 30-day go-shop + Excluded Party tail (6.2) |
| Termination fee tiers | single company fee ($407.5M) | two-tier: $123M / $61.5M go-shop rate |
| Reverse fee | $815M keyed to regulatory failure / breach of efforts | $266.4M keyed to Parent breach / failure to close (financing failure) |
| Financing docs | Debt Commitment Letter only; no equity backstop | Debt + Equity Commitment Letters; Limited Guarantee; Marketing Period; Solvency rep; No Recourse (9.14) |
| Outside date | Jan 9, 2025 + 3 automatic quarterly extensions | Dec 23, 2025 fixed |
| Regulatory covenant | Remedy Actions (divestiture obligation) | plain reasonable best efforts |
| Governance extras | none | Voting Agreements signed at signing |

Shared parser rules confirmed on both: TOC strip = drop everything before the second
occurrence of "AGREEMENT AND PLAN OF MERGER"; definitions split between a central list
and inline definitions, so definition chunks need both a list parser and an inline
"the 'Term'" pattern; cross-reference density is high (~5-7 per 1000 words), so chunking
should resolve "Section X.Y" references or at least index them as links between chunks.
