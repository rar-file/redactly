#!/usr/bin/env python3
"""Generate sample_large.pdf — a ~200-page CONFIDENTIAL legal document.

The document mixes realistic legal boilerplate (Master Services Agreement,
Confidential Settlement Agreement and Release, definitions, indemnification,
governing law, confidentiality, limitation of liability) with a very long
"EXHIBIT B — SCHEDULE OF AFFECTED INDIVIDUALS" appendix that scatters large
amounts of fake PII (names, emails, phones, SSNs, dates of birth, addresses,
bank account numbers, employee IDs) so a redactor finds hundreds/thousands of
items.

All people, emails, SSNs, accounts and addresses are randomly generated and
fictitious. Any resemblance to a real person is coincidental.
"""

import os
import re
import random

import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample_large.pdf")

random.seed(20260629)

# ----------------------------------------------------------------- layout
PAGE_W, PAGE_H = 612.0, 792.0          # US Letter
MARGIN_L, MARGIN_R = 60.0, 60.0
TOP = 92.0                              # first baseline (below header rule)
BOTTOM = 720.0                          # do not draw body text past this y
TEXT_W = PAGE_W - MARGIN_L - MARGIN_R   # 492 pt

HEADER = "CONFIDENTIAL — ATTORNEY WORK PRODUCT"
FOOTER_NOTE = "CONFIDENTIAL — SUBJECT TO PROTECTIVE ORDER"

BODY = "tiro"     # Times-Roman
BOLD = "tibo"     # Times-Bold
ITAL = "tiit"     # Times-Italic
SANS = "hebo"     # Helvetica-Bold (header/footer)

BLACK = (0, 0, 0)
GREY = (0.40, 0.40, 0.40)
NAVY = (0.10, 0.13, 0.32)

# ----------------------------------------------------------------- data pools
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Karen", "Charles", "Sarah", "Daniel",
    "Nancy", "Matthew", "Margaret", "Anthony", "Lisa", "Mark", "Betty",
    "Donald", "Dorothy", "Steven", "Sandra", "Paul", "Ashley", "Andrew",
    "Kimberly", "Joshua", "Donna", "Kenneth", "Emily", "Kevin", "Carol",
    "Brian", "Michelle", "George", "Amanda", "Edward", "Melissa", "Ronald",
    "Deborah", "Priya", "Wei", "Carlos", "Fatima", "Hiroshi", "Olga",
    "Diego", "Amara", "Sven", "Leila",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Okafor", "Petrov", "Khan", "Nakamura", "Schmidt",
    "Costa", "Andersson", "Haddad", "Kowalski", "Reyes",
]

STREETS = [
    "Maple Ridge Drive", "Oakhurst Avenue", "Sycamore Lane", "Birchwood Court",
    "Cedar Hollow Road", "Willow Creek Way", "Magnolia Boulevard", "Aspen Grove Street",
    "Juniper Terrace", "Linden Park Place", "Hawthorne Circle", "Cypress Point Drive",
    "Chestnut Hill Road", "Elmwood Avenue", "Dogwood Lane", "Spruce Meadow Way",
    "Poplar Bend Court", "Redwood Crossing", "Brookside Trail", "Harvest Moon Road",
    "Sunset Ridge Drive", "Stonegate Avenue", "Meadowlark Lane", "Whispering Pines Road",
    "Founders Square", "Riverbend Drive", "Lakeshore Boulevard", "Heatherfield Court",
    "Wexford Place", "Camden Row",
]

CITIES = [
    ("San Francisco", "CA"), ("Austin", "TX"), ("Denver", "CO"), ("Seattle", "WA"),
    ("Portland", "OR"), ("Chicago", "IL"), ("Boston", "MA"), ("Atlanta", "GA"),
    ("Phoenix", "AZ"), ("Nashville", "TN"), ("Columbus", "OH"), ("Raleigh", "NC"),
    ("Minneapolis", "MN"), ("Madison", "WI"), ("Boulder", "CO"), ("Tacoma", "WA"),
    ("Arlington", "VA"), ("Sacramento", "CA"), ("Tucson", "AZ"), ("Omaha", "NE"),
    ("Providence", "RI"), ("Spokane", "WA"), ("Fresno", "CA"), ("Akron", "OH"),
]

DOMAINS = [
    "northgate-holdings.com", "meridianlabs.io", "atlasdyne.com", "vertexpartners.net",
    "summitclaims.org", "brightpathhr.com", "cloverfield-mail.com", "quantanovus.com",
    "harborline.co", "stonebridgegroup.com", "evergreensys.net", "pinnacleworks.io",
    "fairwindfinancial.com", "redoaklegal.com", "lumenworks.io",
]

BANKS = [
    "First National Trust", "Harbor Federal Credit Union", "Summit Pacific Bank",
    "Cedarstone Savings", "Meridian Community Bank", "Crosspoint Financial",
    "Granite Mutual Bank", "Lakeside Credit Union", "Ironwood Bank & Trust",
    "Beacon Heritage Bank",
]

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# uniqueness trackers (maximize what the redactor counts)
_used_ssn, _used_email, _used_acct, _used_phone = set(), set(), set(), set()


def _uniq(gen, used):
    for _ in range(50):
        v = gen()
        if v not in used:
            used.add(v)
            return v
    used.add(v)
    return v


def make_ssn():
    return _uniq(lambda: "%03d-%02d-%04d" % (
        random.randint(101, 899), random.randint(10, 99), random.randint(1000, 9999)),
        _used_ssn)


def make_phone():
    return _uniq(lambda: "(%03d) %03d-%04d" % (
        random.randint(201, 989), random.randint(201, 989), random.randint(0, 9999)),
        _used_phone)


def make_account():
    # 12-16 digit standalone number -> matches the redactor's account pattern
    return _uniq(lambda: "".join(str(random.randint(0, 9))
                                 for _ in range(random.choice([12, 13, 14, 16]))),
                 _used_acct)


def make_email(first, last, idx):
    base = "%s.%s" % (first.lower(), last.lower())
    def gen():
        style = random.random()
        if style < 0.4:
            local = "%s%d" % (base, random.randint(1, 998))
        elif style < 0.7:
            local = "%s_%s%d" % (first[0].lower(), last.lower(), random.randint(1, 99))
        else:
            local = "%s.%s" % (base, random.choice(["hr", "case", "ref", str(idx)]))
        return "%s@%s" % (local, random.choice(DOMAINS))
    return _uniq(gen, _used_email)


def make_address():
    num = random.randint(101, 9899)
    street = random.choice(STREETS)
    city, st = random.choice(CITIES)
    zip5 = random.randint(10001, 99950)
    unit = ""
    if random.random() < 0.35:
        unit = ", %s %d" % (random.choice(["Apt", "Suite", "Unit", "#"]),
                            random.randint(1, 480))
    return "%d %s%s, %s, %s %05d" % (num, street, unit, city, st, zip5)


def make_dob():
    return "%s %d, %d" % (random.choice(MONTHS), random.randint(1, 28),
                          random.randint(1948, 1998))


def make_person():
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    mid = random.choice("ABCDEFGHJKLMNPRSTW")
    return first, mid, last


# ----------------------------------------------------------------- text engine
_wrap_cache = {}


def text_len(s, font, size):
    return fitz.get_text_length(s, fontname=font, fontsize=size)


def wrap(text, font, size, width):
    """Greedy word-wrap to a pixel width; returns a list of lines."""
    out = []
    for para_piece in text.split("\n"):
        words = para_piece.split()
        if not words:
            out.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            trial = cur + " " + w
            if text_len(trial, font, size) <= width:
                cur = trial
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out or [""]


class Writer:
    def __init__(self, doc):
        self.doc = doc
        self.page = None
        self.y = TOP
        self.new_page()

    def new_page(self):
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        # running header
        self.page.insert_text((MARGIN_L, 52), HEADER, fontname=SANS,
                              fontsize=8.5, color=GREY)
        self.page.draw_line((MARGIN_L, 60), (PAGE_W - MARGIN_R, 60),
                            color=GREY, width=0.6)
        self.y = TOP

    def ensure(self, need):
        if self.y + need > BOTTOM:
            self.new_page()

    def space(self, h):
        self.y += h
        if self.y > BOTTOM:
            self.new_page()

    def para(self, text, font=BODY, size=10.5, leading=13.5,
             indent=0.0, gap_after=6.0, color=BLACK, justify=False,
             keep=False):
        """Render a wrapped paragraph, breaking across pages as needed."""
        width = TEXT_W - indent
        lines = wrap(text, font, size, width)
        if keep:
            self.ensure(len(lines) * leading + gap_after)
        for i, line in enumerate(lines):
            self.ensure(leading)
            x = MARGIN_L + indent
            if justify and i < len(lines) - 1 and line.count(" ") >= 1 \
                    and text_len(line, font, size) > width * 0.55:
                self._justified(line, x, width, font, size, color)
            else:
                self.page.insert_text((x, self.y), line, fontname=font,
                                      fontsize=size, color=color)
            self.y += leading
        self.y += gap_after

    def _justified(self, line, x, width, font, size, color):
        words = line.split(" ")
        if len(words) == 1:
            self.page.insert_text((x, self.y), line, fontname=font,
                                  fontsize=size, color=color)
            return
        words_w = sum(text_len(w, font, size) for w in words)
        gap = (width - words_w) / (len(words) - 1)
        cx = x
        for w in words:
            self.page.insert_text((cx, self.y), w, fontname=font,
                                  fontsize=size, color=color)
            cx += text_len(w, font, size) + gap

    def heading(self, text, size=13, gap_before=12, gap_after=7,
                color=NAVY, font=BOLD, center=False):
        self.space(gap_before)
        self.ensure(size + 4)
        if center:
            w = text_len(text, font, size)
            x = MARGIN_L + (TEXT_W - w) / 2.0
        else:
            x = MARGIN_L
        self.page.insert_text((x, self.y), text, fontname=font,
                              fontsize=size, color=color)
        self.y += size + 2
        self.y += gap_after

    def kv(self, label, value, label_w=126.0, size=10.5, leading=13.5,
           value_font=BODY):
        """Label + value row used by the affected-individual records."""
        self.ensure(leading)
        self.page.insert_text((MARGIN_L, self.y), label, fontname=BOLD,
                              fontsize=size, color=BLACK)
        vx = MARGIN_L + label_w
        for line in wrap(value, value_font, size, TEXT_W - label_w):
            self.page.insert_text((vx, self.y), line, fontname=value_font,
                                  fontsize=size, color=BLACK)
            self.y += leading
            self.ensure(leading)
        # (loop already advanced y once per line)

    def rule(self, color=GREY, width=0.5, gap=4):
        self.ensure(gap + 2)
        self.page.draw_line((MARGIN_L, self.y - 3), (PAGE_W - MARGIN_R, self.y - 3),
                            color=color, width=width)
        self.y += gap


# ----------------------------------------------------------------- legalese
def lipsum_legal(n):
    """Deterministic dense legal-style filler sentences."""
    subjects = [
        "Each Party", "The Disclosing Party", "The Receiving Party",
        "The Indemnifying Party", "Service Provider", "Client", "Releasor",
        "Releasee", "The Settling Parties", "Counsel of record",
    ]
    verbs = [
        "shall indemnify, defend, and hold harmless",
        "hereby irrevocably waives any right to",
        "acknowledges and agrees that it shall not",
        "represents and warrants that it has the full corporate power to",
        "covenants that it will at all times comply with",
        "expressly disclaims all liability arising from",
        "shall use commercially reasonable efforts to",
        "agrees that time is of the essence with respect to",
    ]
    objects = [
        "any and all claims, demands, losses, and causes of action arising hereunder",
        "the confidential information disclosed pursuant to this Agreement",
        "the limitations of liability set forth in Section 9 below",
        "the governing law and exclusive venue provisions of this Agreement",
        "all obligations of confidentiality surviving termination",
        "any consequential, incidental, special, or punitive damages",
        "the schedule of affected individuals attached as Exhibit B",
        "the mutual general release of all known and unknown claims",
    ]
    tails = [
        "to the fullest extent permitted by applicable law.",
        "notwithstanding any provision to the contrary herein.",
        "subject to the terms and conditions set forth herein.",
        "without regard to its conflict-of-laws principles.",
        "and the parties intend this provision to be enforced as written.",
        "except as otherwise expressly provided in this Agreement.",
    ]
    out = []
    for _ in range(n):
        out.append("%s %s %s, %s" % (
            random.choice(subjects), random.choice(verbs),
            random.choice(objects), random.choice(tails)))
    return " ".join(out)


def front_matter(w):
    # ---- title page ---------------------------------------------------
    w.space(70)
    w.heading("MASTER SERVICES AGREEMENT", size=22, gap_before=0, gap_after=10,
              center=True, color=NAVY)
    w.heading("AND", size=12, gap_before=2, gap_after=6, center=True, color=GREY)
    w.heading("CONFIDENTIAL SETTLEMENT AGREEMENT AND RELEASE",
              size=16, gap_before=4, gap_after=18, center=True, color=NAVY)
    w.para("This Master Services Agreement and the Confidential Settlement "
           "Agreement and Release (collectively, the “Agreement”) is "
           "entered into as of July 1, 2026 (the “Effective Date”), by "
           "and between the parties identified below.", justify=True, gap_after=14)

    w.heading("PARTIES", size=12)
    w.para("NORTHGATE HOLDINGS, INC., a Delaware corporation, with its "
           "principal place of business at 1200 Founders Square, Suite 900, "
           "Wilmington, DE 19801 (“Company” or “Service "
           "Provider”); and", justify=True)
    w.para("MERIDIAN LABS, LLC, a California limited liability company, with "
           "offices at 4820 Cedar Hollow Road, San Francisco, CA 94114 "
           "(“Client”). The Company and the Client are referred to "
           "herein individually as a “Party” and collectively as the "
           "“Parties.”", justify=True, gap_after=12)

    w.heading("PRINCIPAL CONTACTS", size=12)
    contacts = [
        ("For Company:", "Gregory T. Halloran, General Counsel",
         "ghalloran@northgate-holdings.com", "(415) 555-0172"),
        ("For Client:", "Renata K. Oyelaran, VP Legal Affairs",
         "royelaran@meridianlabs.io", "(628) 555-0145"),
        ("Settlement Administrator:", "Dana P. Whitmore, Esq.",
         "dwhitmore@redoaklegal.com", "(312) 555-0190"),
    ]
    for role, person, email, phone in contacts:
        w.kv(role.replace(":", ""), "%s  |  %s  |  %s" % (person, email, phone),
             label_w=150)
    w.space(10)

    # ---- recitals -----------------------------------------------------
    w.heading("RECITALS", size=13)
    for lead in ["WHEREAS,", "WHEREAS,", "WHEREAS,", "NOW, THEREFORE,"]:
        w.para(lead + " " + lipsum_legal(3), justify=True)

    # ---- numbered articles -------------------------------------------
    articles = [
        ("1. DEFINITIONS",
         "As used in this Agreement, the following capitalized terms shall "
         "have the meanings set forth below. " + lipsum_legal(6),
         [("“Affected Individual”", "means any natural person whose "
           "personal information is identified in the Schedule of Affected "
           "Individuals attached hereto as Exhibit B."),
          ("“Confidential Information”", "means all non-public "
           "information disclosed by one Party to the other, whether oral, "
           "written, or electronic, that is designated as confidential."),
          ("“Personal Information”", "means information that "
           "identifies, relates to, or could reasonably be linked with a "
           "particular individual, including name, email address, telephone "
           "number, Social Security number, date of birth, residential "
           "address, financial account number, and employee identifier.")]),
        ("2. SCOPE OF SERVICES",
         lipsum_legal(8), []),
        ("3. COMPENSATION AND PAYMENT TERMS",
         lipsum_legal(7), []),
        ("4. TERM AND TERMINATION",
         lipsum_legal(7), []),
        ("5. CONFIDENTIALITY",
         "Each Party acknowledges that it may receive Confidential "
         "Information of the other Party. " + lipsum_legal(7), []),
        ("6. DATA PROTECTION AND PERSONAL INFORMATION",
         "The Parties shall process Personal Information relating to each "
         "Affected Individual solely as necessary to administer this "
         "Agreement. " + lipsum_legal(6), []),
        ("7. INDEMNIFICATION",
         "The Indemnifying Party shall indemnify, defend, and hold harmless "
         "the Indemnified Party. " + lipsum_legal(8), []),
        ("8. REPRESENTATIONS AND WARRANTIES",
         lipsum_legal(7), []),
        ("9. LIMITATION OF LIABILITY",
         "EXCEPT FOR A PARTY'S INDEMNIFICATION OBLIGATIONS, IN NO EVENT SHALL "
         "EITHER PARTY BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, "
         "CONSEQUENTIAL, OR PUNITIVE DAMAGES. " + lipsum_legal(6), []),
        ("10. GOVERNING LAW AND VENUE",
         "This Agreement shall be governed by and construed in accordance "
         "with the laws of the State of Delaware, without regard to its "
         "conflict-of-laws principles. " + lipsum_legal(6), []),
        ("11. DISPUTE RESOLUTION",
         lipsum_legal(7), []),
        ("12. GENERAL PROVISIONS",
         lipsum_legal(8), []),
    ]
    for title, body, defs in articles:
        w.heading(title, size=12)
        w.para(body, justify=True)
        for term, meaning in defs:
            w.para(term + " " + meaning, indent=18, justify=True, gap_after=4)

    # ---- settlement portion ------------------------------------------
    w.new_page()
    w.heading("CONFIDENTIAL SETTLEMENT AGREEMENT AND RELEASE",
              size=15, gap_before=20, gap_after=12, center=True, color=NAVY)
    w.para("This Confidential Settlement Agreement and Release (this "
           "“Settlement”) is made and entered into by and among the "
           "Parties to resolve fully and finally all disputes relating to the "
           "matters described in Exhibit B, without any admission of liability.",
           justify=True, gap_after=10)
    settle = [
        ("A. MUTUAL GENERAL RELEASE",
         "In consideration of the mutual promises herein, each Party, on "
         "behalf of itself and its successors and assigns, hereby releases "
         "and forever discharges the other Party. " + lipsum_legal(7)),
        ("B. SETTLEMENT CONSIDERATION",
         lipsum_legal(6)),
        ("C. CONFIDENTIALITY OF SETTLEMENT",
         "The Parties agree to keep the terms of this Settlement strictly "
         "confidential. " + lipsum_legal(6)),
        ("D. NON-DISPARAGEMENT", lipsum_legal(5)),
        ("E. NO ADMISSION OF LIABILITY", lipsum_legal(5)),
    ]
    for title, body in settle:
        w.heading(title, size=12)
        w.para(body, justify=True)

    # ---- signature blocks --------------------------------------------
    w.heading("IN WITNESS WHEREOF", size=12, gap_before=14)
    w.para("The Parties have executed this Agreement as of the Effective Date "
           "by their duly authorized representatives.", justify=True, gap_after=18)
    sigs = [
        ("NORTHGATE HOLDINGS, INC.", "Gregory T. Halloran", "General Counsel",
         "ghalloran@northgate-holdings.com", "(415) 555-0172"),
        ("MERIDIAN LABS, LLC", "Renata K. Oyelaran", "VP, Legal Affairs",
         "royelaran@meridianlabs.io", "(628) 555-0145"),
    ]
    for org, name, title, email, phone in sigs:
        w.ensure(90)
        w.para(org, font=BOLD, size=11, gap_after=20)
        w.page.draw_line((MARGIN_L, w.y - 6), (MARGIN_L + 250, w.y - 6),
                         color=BLACK, width=0.7)
        w.para("By: %s" % name, gap_after=2)
        w.para("Title: %s" % title, gap_after=2)
        w.para("Email: %s    Phone: %s" % (email, phone), gap_after=2)
        w.para("Date: ______________________", gap_after=18)

    w.new_page()


# ----------------------------------------------------------------- exhibit B
EXHIBIT_NOTES = [
    "The personal information set forth in this record is maintained under "
    "seal and may be disclosed only to counsel of record and the Settlement "
    "Administrator pursuant to the Protective Order entered in this matter.",
    "This Affected Individual was identified through the data-mapping "
    "process described in Section 6 and is entitled to notice under the terms "
    "of the Settlement. " ,
    "Records in this Schedule are illustrative and were generated for "
    "administrative purposes; redaction of all Personal Information is "
    "required prior to any public filing.",
    "The Settlement Administrator shall verify the contact information below "
    "before issuing the individual notice and any associated settlement "
    "payment to the Affected Individual.",
]


def exhibit_b(w, target_pages):
    w.heading("EXHIBIT B — SCHEDULE OF AFFECTED INDIVIDUALS",
              size=15, gap_before=18, gap_after=10, center=True, color=NAVY)
    w.para("The following Schedule lists each Affected Individual together with "
           "the categories of Personal Information maintained in connection "
           "with the matters resolved by this Settlement. ALL ENTRIES ARE "
           "CONFIDENTIAL and must be redacted prior to public filing. This "
           "Schedule is continued across the following pages.",
           justify=True, gap_after=12)

    idx = 0
    while w.doc.page_count < target_pages:
        idx += 1
        first, mid, last = make_person()
        full = "%s %s. %s" % (first, mid, last)
        email = make_email(first, last, idx)
        phone = make_phone()
        ssn = make_ssn()
        dob = make_dob()
        addr = make_address()
        acct = make_account()
        bank = random.choice(BANKS)
        emp_id = "EMP-%06d" % random.randint(100000, 999999)
        case_no = "NG-2026-%05d" % idx

        # keep a record block together when it comfortably fits
        if w.y + 150 > BOTTOM:
            w.new_page()

        w.heading("Record No. %04d  —  Affected Individual  (Case %s)"
                  % (idx, case_no), size=11, gap_before=6, gap_after=5,
                  color=NAVY, font=BOLD)
        w.kv("Full Name:", full)
        w.kv("Email:", email)
        w.kv("Phone:", phone)
        w.kv("Social Security Number:", ssn)
        w.kv("Date of Birth:", dob)
        w.kv("Home Address:", addr)
        w.kv("Bank Account Number:", "%s  (%s)" % (acct, bank))
        w.kv("Employee ID:", emp_id)
        w.space(2)
        w.para(random.choice(EXHIBIT_NOTES), size=9.5, leading=12, indent=8,
               color=GREY, justify=True, gap_after=6)
        w.rule()

        # interleave legal paragraphs periodically
        if idx % 6 == 0:
            w.para("CONTINUING OBLIGATIONS. " + lipsum_legal(3),
                   size=10, leading=13, justify=True, gap_after=8)
        if idx % 23 == 0:
            w.heading("CERTIFICATION OF CUSTODIAN OF RECORDS", size=11,
                      gap_before=6, gap_after=5)
            w.para("The undersigned custodian certifies that the foregoing "
                   "records are true and correct copies maintained in the "
                   "ordinary course of business. " + lipsum_legal(2),
                   justify=True, gap_after=8)

    # closing
    w.heading("END OF EXHIBIT B", size=12, gap_before=14, center=True, color=NAVY)
    w.para("The Schedule of Affected Individuals concludes above. All Personal "
           "Information contained in this Exhibit is CONFIDENTIAL and subject "
           "to the Protective Order. " + lipsum_legal(2), justify=True)
    return idx


def add_footers(doc):
    total = doc.page_count
    for i, page in enumerate(doc, start=1):
        page.draw_line((MARGIN_L, 742), (PAGE_W - MARGIN_R, 742),
                       color=GREY, width=0.6)
        page.insert_text((MARGIN_L, 758), FOOTER_NOTE, fontname=SANS,
                         fontsize=7.5, color=GREY)
        label = "Page %d of %d" % (i, total)
        w = fitz.get_text_length(label, fontname="helv", fontsize=8)
        page.insert_text((PAGE_W - MARGIN_R - w, 758), label,
                         fontname="helv", fontsize=8, color=GREY)


# ----------------------------------------------------------------- main
def main():
    doc = fitz.open()
    doc.set_metadata({
        "title": "Master Services Agreement & Confidential Settlement (DEMO)",
        "author": "Redactly Demo Generator",
        "subject": "CONFIDENTIAL - ATTORNEY WORK PRODUCT",
        "keywords": "confidential, settlement, exhibit b, PII, demo",
    })
    w = Writer(doc)
    front_matter(w)
    n_records = exhibit_b(w, target_pages=200)
    add_footers(doc)
    doc.save(OUT, deflate=True, garbage=4)
    page_count = doc.page_count
    doc.close()

    # ---- report embedded PII counts using the redactor's own patterns ----
    rdoc = fitz.open(OUT)
    full = "".join(p.get_text() for p in rdoc)
    rdoc.close()

    pat_email = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
    pat_ssn = r"\b\d{3}-\d{2}-\d{4}\b"
    pat_phone = r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    pat_acct = r"\b\d{12,16}\b"

    emails = re.findall(pat_email, full)
    ssns = re.findall(pat_ssn, full)
    phones = re.findall(pat_phone, full)
    accts = re.findall(pat_acct, full)

    size_mb = os.path.getsize(OUT) / (1024.0 * 1024.0)

    print("=" * 60)
    print("Generated:        %s" % OUT)
    print("Records (Exhibit B): %d" % n_records)
    print("Final page count: %d" % page_count)
    print("File size:        %.2f MB" % size_mb)
    print("-" * 60)
    print("Embedded PII (occurrences / unique values):")
    print("  SSNs:            %5d / %5d" % (len(ssns), len(set(ssns))))
    print("  Emails:          %5d / %5d" % (len(emails), len(set(emails))))
    print("  Account numbers: %5d / %5d" % (len(accts), len(set(accts))))
    print("  Phones:          %5d / %5d" % (len(phones), len(set(phones))))
    approx_total = len(ssns) + len(emails) + len(accts) + len(phones)
    print("  Approx PII (these 4 categories): %d occurrences" % approx_total)
    print("=" * 60)


if __name__ == "__main__":
    main()
