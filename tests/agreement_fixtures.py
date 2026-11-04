"""Small fake agreements in the three heading styles seen on EDGAR.

They copy the layout quirks from the reading notes, not the legal content.
"""

LONG = "and the parties further agree to the matters set forth in this paragraph " * 4

# Style 1 (HPE/Juniper): arabic articles, "Section 10.01." on its own line or table cell,
# term/section index table at the end of the definitions section.
ARABIC_PREFIXED = f"""
<html><body>
<p>AGREEMENT AND PLAN OF MERGER</p>
<p>TABLE OF CONTENTS</p>
<table>
<tr><td>ARTICLE 1</td></tr><tr><td>DEFINITIONS</td></tr>
<tr><td>Section 1.01.</td><td>Definitions</td><td>1</td></tr>
<tr><td>Section 1.02.</td><td>Other Definitional Provisions</td><td>2</td></tr>
<tr><td>ARTICLE 2</td></tr><tr><td>THE MERGER</td></tr>
<tr><td>Section 2.01.</td><td>The Merger</td><td>3</td></tr>
</table>
<p>i</p>
<p>AGREEMENT AND PLAN OF MERGER</p>
<p>AGREEMENT AND PLAN OF MERGER (this “Agreement”) dated as of January 9, 2024
among Juniper Networks, Inc., a Delaware corporation (the “Company”), {LONG}</p>
<p>WHEREAS, the board of directors of the Company has approved this Agreement {LONG}</p>
<p>ARTICLE 1</p>
<p>DEFINITIONS</p>
<table><tr><td>Section 1.01.</td><td>Definitions.</td></tr></table>
<p>(a) As used in this Agreement, the following terms have the following meanings:</p>
<p>“Acquisition Proposal” means any offer or proposal from a Third Party {LONG}</p>
<p>“Company Material Adverse Effect” means any effect that is material, except:</p>
<p>(i) changes in general economic conditions;</p>
<p>(ii) changes in law.</p>
<p>“Superior Proposal” has the meaning set forth in Section 6.03(e).</p>
<p>(b) Each of the following terms is defined in the Section set forth opposite such term:</p>
<table>
<tr><td>Term</td><td>Section</td></tr>
<tr><td>Burdensome Condition</td><td>8.01(b)</td></tr>
<tr><td>Company Termination Fee</td><td>11.04(b)(i)</td></tr>
<tr><td>Effective Time</td><td>2.01(c)</td></tr>
<tr><td>End Date</td><td>10.01(b)(i)</td></tr>
<tr><td>Merger Consideration</td><td>2.02(a)</td></tr>
</table>
<p>Section 1.02.</p>
<p>Other Definitional and Interpretative Provisions.</p>
<p>The words “hereof” and “herein” refer to this Agreement as a whole {LONG}</p>
<p>1</p>
<p><a href="#toc">Table of Contents</a></p>
<p>ARTICLE 2</p>
<p>THE MERGER</p>
<p>Section 2.01.</p>
<p>The Merger.</p>
<p>At the Effective Time, Merger Subsidiary shall be merged with and into the Company.</p>
<p>Section 2.02.</p>
<p>Conversion of Shares.</p>
<p>(a) Each Share shall be converted into the right to receive $40.00 per Share in cash,
without interest (the “Merger Consideration”).</p>
<p>Section 2.02(b) shall not apply to Dissenting Shares.</p>
<p>ARTICLE 3</p>
<p>TERMINATION</p>
<p>Section 3.01.</p>
<p>Termination.</p>
<p>This Agreement may be terminated if the Effective Time has not occurred on or before
January 9, 2025 (the “End Date”).</p>
<p>Section 3.02.</p>
<p>[Reserved].</p>
<p>[Remainder of page intentionally left blank; signature page follows]</p>
<p>IN WITNESS WHEREOF, the parties have caused this Agreement to be executed.</p>
<p>JUNIPER NETWORKS, INC.</p>
<p>EXHIBIT A</p>
<p>FORM OF CERTIFICATE OF INCORPORATION OF THE SURVIVING CORPORATION</p>
</body></html>
"""

# Style 2 (D&B/Clearlake): roman articles, bare "8.2" labels, titles split over several
# lines with a lone period, index of defined terms in the front matter.
ROMAN_BARE = f"""
<html><body>
<p>EXECUTION VERSION</p>
<p>AGREEMENT AND PLAN OF MERGER</p>
<p>TABLE OF CONTENTS</p>
<p>ARTICLE I</p><p>THE MERGER</p>
<p>1.1</p><p>The Merger</p><p>1</p>
<p>1.2</p><p>Closing</p><p>1</p>
<p>iii</p>
<p>INDEX OF DEFINED TERMS</p>
<table>
<tr><td>Defined Term</td><td>Section</td></tr>
<tr><td>“Acceptable Confidentiality Agreement”</td><td>9.15</td></tr>
<tr><td>“Agreement”</td><td>Preamble</td></tr>
<tr><td>“Excluded Party”</td><td>9.15</td></tr>
<tr><td>“Go-Shop Period”</td><td>6.2(a)(i)</td></tr>
<tr><td>“Merger Consideration”</td><td>3.1(a)(i)</td></tr>
</table>
<p>iv</p>
<p>AGREEMENT AND PLAN OF MERGER</p>
<p>This AGREEMENT AND PLAN OF MERGER (this “Agreement”), is entered into as of
March 23, 2025, by and among Dun &amp; Bradstreet Holdings, Inc. {LONG}</p>
<p>ARTICLE I</p>
<p>THE MERGER</p>
<p><b>1.1</b></p><p><u>The Merger</u></p><p>.</p>
<p>Upon the terms and subject to the conditions set forth in this Agreement {LONG}</p>
<p><b>1.2</b></p><p><u>Closing</u></p><p>.</p>
<p>The closing of the Merger shall take place at 10:00 a.m. Eastern Time {LONG}</p>
<p>ARTICLE II</p>
<p>ORGANIZATIONAL DOCUMENTS, DIRECTORS AND OFFICERS</p>
<p>OF THE SURVIVING CORPORATION</p>
<p><b>2.1</b></p><p><u>Certificate of Incorporation</u></p><p>.</p>
<p>The certificate of incorporation of the Company shall be amended {LONG}</p>
<p>ARTICLE III</p>
<p style="text-transform: uppercase">termination</p>
<p><b>3.1</b></p><p><u>Termination</u></p><p><u>by Either Parent or the Company</u></p><p>.</p>
<p>This Agreement may be terminated if the Merger shall not have been consummated by
December 23, 2025 (such date, the “Termination Date”).</p>
<p><b>3.2</b></p><p><u>Definitions</u></p><p>.</p>
<p>For purposes of this Agreement, the following terms shall have the meanings below:</p>
<p>“Excluded Party” means any Person from whom the Company has received a bona fide
written Acquisition Proposal before the No-Shop Period Start Date.</p>
<p>IN WITNESS WHEREOF, the parties have executed this Agreement.</p>
</body></html>
"""

# Style 3: heading, title and body on one line; uppercase SECTION; word article numbers;
# paragraphs that begin with numbers or cross-references and must not become headings.
SAME_LINE = f"""
<html><body>
<p>AGREEMENT AND PLAN OF MERGER, dated as of June 1, 2024 (the “Agreement”), by and
among Alpha Corp., Beta Inc. and Gamma Sub, Inc. {LONG}</p>
<p>ARTICLE ONE THE MERGER</p>
<p>SECTION 1.1 Definitions. As used in this Agreement the following terms apply {LONG}</p>
<p>(a) “Acceptable Confidentiality Agreement” means a customary confidentiality agreement.</p>
<p>(b) “Business Day” means any day other than a Saturday, Sunday or bank holiday.</p>
<p>(i) for this purpose, a half day counts as a full day.</p>
<p>SECTION 1.2 Certain U.S. Tax Matters. The parties intend the Merger to qualify {LONG}</p>
<p>(c) As used in this Agreement, the term “Tax” or “Taxes” means all federal and
state taxes. The Company has filed all Tax Returns.</p>
<p>1.5 million shares of preferred stock shall be cancelled at the Effective Time.</p>
<p>ARTICLE TWO TERMINATION</p>
<p>Section 2.01 Termination. This Agreement may be terminated at any time {LONG}</p>
<p>Section 2.03 shall survive any termination of this Agreement.</p>
<p>Section 2.02 Termination Fee. (a) The Company shall pay $10,000,000 (the
“Termination Fee”) to Parent.</p>
<p>IN WITNESS WHEREOF, the parties have executed this Agreement.</p>
</body></html>
"""

# Style 4 (tender offer, e.g. CymaBay/Gilead): ("Agreement") with no "this", no IN
# WITNESS line, definitions in Exhibit A and the offer conditions in Annex I after the
# signature pages, plus a form of charter that should be dropped.
TENDER_OFFER = f"""
<html><body>
<p>Exhibit 2.1</p>
<p>TABLE OF CONTENTS</p>
<p>Exhibit A</p><p>Certain Definitions</p>
<p>Annex I</p><p>Conditions to the Offer</p>
<p>AGREEMENT AND PLAN OF MERGER</p>
<p>THIS AGREEMENT AND PLAN OF MERGER (\u201cAgreement\u201d) is made and entered into as of
February 11, 2024 by and among Gilead Sciences, Inc. and CymaBay Therapeutics, Inc. {LONG}</p>
<p>ARTICLE I</p>
<p>THE OFFER</p>
<p>1.1 The Offer. Purchaser shall commence the Offer as promptly as practicable {LONG}</p>
<p>ARTICLE II</p>
<p>TERMINATION</p>
<p>2.1 Termination. This Agreement may be terminated before the Offer Acceptance Time.</p>
<p>[Signature Page Follows]</p>
<p>GILEAD SCIENCES, INC.</p>
<p>By: /s/ Name</p>
<p>[Signature Page to Agreement and Plan of Merger]</p>
<p>Exhibit A</p>
<p>Certain Definitions</p>
<p>\u201cAffiliate\u201d shall mean, as to any Person, any other Person that controls it.</p>
<p>\u201cAgreement\u201d is defined in the preamble to the Agreement.</p>
<p>A-1</p>
<p>Exhibit A</p>
<p>\u201cCompany RSUs\u201d means all awards of restricted stock units.</p>
<p>Annex I</p>
<p>Conditions to the Offer</p>
<p>Purchaser shall not be required to accept for payment any shares unless the Minimum
Condition has been satisfied.</p>
<p>Annex II</p>
<p>Amended and Restated Certificate of Incorporation of CymaBay Therapeutics, Inc.</p>
<p>FIRST: The name of the corporation is CymaBay Therapeutics, Inc.</p>
</body></html>
"""

# Style 5 (Ansys/Synopsys): "Section 1. THE TRANSACTION" is the top level, sections are
# numbered 1.1, 1.2; the contents page lists them too.
SECTION_TOP_LEVEL = f"""
<html><body>
<p>Page</p>
<p>SECTION 1.</p><p>THE TRANSACTION</p>
<p>1.1</p><p>The Merger</p><p>1.2</p><p>Effects of the Merger</p><p>1.3</p><p>Closing</p>
<p>1.4</p><p>Charter</p><p>1.5</p><p>Bylaws</p><p>1.6</p><p>Directors</p>
<p>SECTION 2.</p><p>MISCELLANEOUS PROVISIONS</p>
<p>2.1</p><p>Amendment</p>
<p>AGREEMENT AND PLAN OF MERGER (this “Agreement”) is made and entered into as of
January 15, 2024, by and among Synopsys, Inc. and ANSYS, Inc. {LONG}</p>
<p>The parties to this Agreement, intending to be legally bound, agree as follows:</p>
<p>Section 1. THE TRANSACTION</p>
<p>1.1 The Merger. Upon the terms and subject to the conditions set forth in this Agreement.</p>
<p>1.2 Effects of the Merger. The Merger shall have the effects set forth in the DGCL.</p>
<p>Section 5 of the Securities Act shall not apply to the issuance of the shares.</p>
<p>Section 2. MISCELLANEOUS PROVISIONS</p>
<p>2.1 Amendment. This Agreement may be amended by the parties at any time.</p>
<p>IN WITNESS WHEREOF, the parties have caused this Agreement to be executed.</p>
</body></html>
"""
