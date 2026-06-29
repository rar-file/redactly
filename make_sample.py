#!/usr/bin/env python3
"""Generate sample.pdf: a fake business doc with obvious fake PII."""
import os
import fitz

HERE = os.path.dirname(os.path.abspath(__file__))

doc = fitz.open()
page = doc.new_page(width=612, height=792)  # US Letter

lines = [
    ("CONFIDENTIAL - Employee Onboarding Record", 18, True),
    ("", 12, False),
    ("Acme Global Industries, Inc.  -  Human Resources Department", 11, False),
    ("Document ID: HR-2026-00471        Date: June 29, 2026", 11, False),
    ("", 10, False),
    ("This record contains sensitive personnel information and is intended", 11, False),
    ("solely for authorized HR personnel. Unauthorized disclosure is", 11, False),
    ("strictly prohibited under company policy and applicable law.", 11, False),
    ("", 8, False),
    ("EMPLOYEE DETAILS", 13, True),
    ("Full Name:        Jonathan A. Whitfield", 11, False),
    ("Employee ID:      EMP-884213", 11, False),
    ("Email:            jonathan.whitfield@acme-global.com", 11, False),
    ("Phone:            (415) 555-0182", 11, False),
    ("Date of Birth:    March 14, 1987", 11, False),
    ("Social Security:  123-45-6789", 11, False),
    ("Home Address:     2847 Maple Ridge Drive, San Francisco, CA 94114", 11, False),
    ("", 8, False),
    ("PAYROLL & BANKING", 13, True),
    ("Direct Deposit Account:  4815738291036572", 11, False),
    ("Routing Number:          121000358", 11, False),
    ("Annual Salary:           $142,000 USD", 11, False),
    ("", 8, False),
    ("NOTES", 13, True),
    ("Employee has completed all required onboarding training modules and", 11, False),
    ("signed the standard confidentiality and acceptable-use agreements.", 11, False),
    ("Equipment issued: laptop, access badge, and security token.", 11, False),
    ("Manager: Sarah Lindqvist  -  Department: Engineering", 11, False),
    ("", 10, False),
    ("Generated automatically by AcmeHR. Page 1 of 1.", 9, False),
]

x = 54
y = 60
for text, size, bold in lines:
    if text == "":
        y += size
        continue
    fontname = "helv" if not bold else "hebo"
    page.insert_text((x, y), text, fontname=fontname, fontsize=size, color=(0, 0, 0))
    y += size + 8

out = os.path.join(HERE, "sample.pdf")
doc.save(out)
doc.close()
print("wrote", out)
