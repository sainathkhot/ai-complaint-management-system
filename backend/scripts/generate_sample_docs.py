"""Generate realistic sample complaint documents for the demo.

Two PDFs and one email, deliberately different in shape so the extraction tool
is visibly doing work rather than pattern-matching one template:

  1. API complaint  - a formal letter on a formulator's letterhead, prose-heavy,
                      bulk quantities in kg and drums, pharmacopoeial grade.
                      Matches the Metformin HCl example in the demo video.
  2. FDF complaint  - a structured intake form with labelled fields, retail
                      pharmacy, unit quantities.
  3. Email (.eml)   - unstructured, conversational, details scattered mid-prose.

Run:  python scripts/generate_sample_docs.py
Out:  sample_documents/
"""

import os
from email.message import EmailMessage

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_documents")
NAVY = colors.HexColor("#1e3a5f")

styles = getSampleStyleSheet()
S = {
    "company": ParagraphStyle("company", parent=styles["Normal"], fontName="Helvetica-Bold",
                              fontSize=15, textColor=NAVY, spaceAfter=2),
    "sub": ParagraphStyle("sub", parent=styles["Normal"], fontSize=8,
                          textColor=colors.HexColor("#555555"), spaceAfter=1),
    "title": ParagraphStyle("title", parent=styles["Normal"], fontName="Helvetica-Bold",
                            fontSize=12, spaceBefore=12, spaceAfter=8),
    "h": ParagraphStyle("h", parent=styles["Normal"], fontName="Helvetica-Bold",
                        fontSize=9.5, textColor=NAVY, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5,
                           leading=14, alignment=TA_JUSTIFY, spaceAfter=6),
}

TABLE_STYLE = TableStyle([
    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#dddddd")),
])


def _letterhead(story, name, address, extra):
    story.append(Paragraph(name, S["company"]))
    story.append(Paragraph(address, S["sub"]))
    story.append(Paragraph(extra, S["sub"]))


def build_api_complaint():
    """Bulk API complaint — matches the Metformin example from the demo video."""
    path = os.path.join(OUT_DIR, "complaint_metformin_api.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            title="Customer Complaint - Metformin HCl API")
    story = []
    _letterhead(
        story,
        "SUNRISE FORMULATIONS PVT. LTD.",
        "Plot 42, Pharma SEZ, Ankleshwar, Gujarat 393002, India",
        "CIN: U24230GJ2011PTC067412 | Tel: +91 2646 220 118 | qa@sunriseformulations.in",
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph("CUSTOMER COMPLAINT NOTIFICATION", S["title"]))

    story.append(Table([
        ["Reference No.:", "SFPL/QA/CC/2026/0188"],
        ["Date of Complaint:", "18-Jul-2026"],
        ["To:", "Head - Quality Assurance, AIVOA Pharmaceuticals Ltd."],
        ["From:", "Ms. Rekha Nair, Manager - Quality Assurance, Sunrise Formulations Pvt. Ltd."],
        ["Mode of Receipt:", "Email, followed by this formal written notification"],
    ], colWidths=[38 * mm, 128 * mm], style=TABLE_STYLE))

    story.append(Paragraph("1. PRODUCT AND BATCH DETAILS", S["h"]))
    story.append(Table([
        ["Product Name:", "Metformin Hydrochloride API"],
        ["Grade / Standard:", "IP/BP"],
        ["Batch / Lot No.:", "MFH260712A"],
        ["Date of Manufacture:", "12-Jul-2026"],
        ["Date of Expiry:", "11-Jul-2029"],
        ["Quantity Supplied:", "500 kg (20 HDPE drums x 25 kg)"],
        ["Quantity Affected:", "75 kg (3 HDPE drums)"],
        ["Invoice / GRN No.:", "AIV/INV/2026/4471 dated 14-Jul-2026"],
    ], colWidths=[38 * mm, 128 * mm], style=TABLE_STYLE))

    story.append(Paragraph("2. DESCRIPTION OF COMPLAINT", S["h"]))
    story.append(Paragraph(
        "During pre-dispensing sampling and visual inspection carried out at our Ankleshwar "
        "facility on 17-Jul-2026, our QC analysts observed that the material contained in "
        "three of the twenty HDPE drums received under the above batch exhibited a distinct "
        "off-white to pale yellow discolouration, in contrast to the white crystalline powder "
        "described in the approved specification and observed in the remaining seventeen drums "
        "of the same consignment.", S["body"]))
    story.append(Paragraph(
        "Additionally, the affected drums showed evidence of caking and lump formation, with "
        "hard aggregates that did not disperse readily on gentle agitation. The inner LDPE "
        "liner of drum number 7 was found to be improperly heat-sealed, with a visible gap of "
        "approximately 40 mm along the seal line, which we believe may have permitted moisture "
        "ingress during transit or storage.", S["body"]))
    story.append(Paragraph(
        "Preliminary loss-on-drying testing performed on a composite sample drawn from the "
        "three affected drums returned a result of 1.28% w/w, against the specification limit "
        "of not more than 0.50% w/w. The related substances profile is currently under "
        "investigation and results will be shared separately.", S["body"]))
    story.append(Paragraph(
        "The affected drums have been segregated and placed under quarantine in our rejected "
        "materials area pending your investigation. No material from this batch has been "
        "released to production.", S["body"]))

    story.append(Paragraph("3. IMPACT AND ACTION REQUESTED", S["h"]))
    story.append(Paragraph(
        "This batch was scheduled for use in the manufacture of Metformin SR 500 mg tablets "
        "for the domestic market. The shortfall has placed our production schedule at risk. "
        "We request that you initiate a formal investigation under your complaint handling "
        "procedure, provide a root cause analysis and CAPA report within 30 calendar days, "
        "and confirm arrangements for replacement material at the earliest.", S["body"]))
    story.append(Paragraph(
        "We further request confirmation as to whether any other batches manufactured in the "
        "same campaign may be affected.", S["body"]))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Rekha Nair<br/>Manager - Quality Assurance<br/>Sunrise Formulations Pvt. Ltd.<br/>"
        "rekha.nair@sunriseformulations.in | +91 98250 41133", S["body"]))
    doc.build(story)
    return path


def build_fdf_complaint():
    """Finished dosage form complaint — retail pharmacy, structured intake form."""
    path = os.path.join(OUT_DIR, "complaint_amoxicillin_fdf.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            title="Customer Complaint - Amoxicillin Capsules")
    story = []
    _letterhead(
        story,
        "APOLLO PHARMACY - ANDHERI WEST",
        "Shop 3, Lokhandwala Complex, Andheri West, Mumbai 400053, Maharashtra",
        "Drug Licence No.: MH-MZ-207841 | Tel: +91 22 2637 9014",
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph("PRODUCT QUALITY COMPLAINT FORM", S["title"]))

    story.append(Table([
        ["Complaint Ref:", "APL/AW/PQC/2026/0342"],
        ["Date Raised:", "24-Jul-2026"],
        ["Raised By:", "Mr. Vinod Deshpande, Chief Pharmacist"],
        ["Received Via:", "Telephone call to AIVOA customer care, ref. call ID 88214"],
        ["Reported To:", "AIVOA Pharmaceuticals Ltd. - Customer Quality Complaints"],
    ], colWidths=[38 * mm, 128 * mm], style=TABLE_STYLE))

    story.append(Paragraph("PRODUCT DETAILS", S["h"]))
    story.append(Table([
        ["Product Name:", "Amoxicillin Capsules"],
        ["Strength:", "500 mg"],
        ["Dosage Form:", "Hard gelatin capsule, 10 x 10 blister pack"],
        ["Batch No.:", "BMX24601"],
        ["Mfg. Date:", "05-Feb-2026"],
        ["Exp. Date:", "04-Feb-2029"],
        ["Quantity Affected:", "36 capsules (4 blister strips)"],
        ["Quantity Dispensed:", "12 capsules to 2 patients before defect was noticed"],
        ["Storage at Pharmacy:", "Air-conditioned, 22-25 C, humidity logged daily"],
    ], colWidths=[38 * mm, 128 * mm], style=TABLE_STYLE))

    story.append(Paragraph("NATURE OF COMPLAINT", S["h"]))
    story.append(Paragraph(
        "A customer returned a partially used strip on 23-Jul-2026 reporting that the capsules "
        "appeared discoloured. On inspection of our remaining stock from the same batch, our "
        "pharmacist identified that a number of capsules had developed a brownish tinge on the "
        "capsule body, most visible at the join between cap and body. Several capsules also "
        "appeared slightly softened to the touch and one had partially deformed within the "
        "blister cavity.", S["body"]))
    story.append(Paragraph(
        "Two of the affected blister strips showed poor seal integrity, with the foil lifting "
        "at the corner of the cavity. No visible foreign matter was observed inside any "
        "capsule. No adverse reaction has been reported by either of the two patients who "
        "received capsules from this batch, and both were contacted by telephone on "
        "24-Jul-2026 as a precaution.", S["body"]))
    story.append(Paragraph(
        "The remaining stock has been removed from the dispensing shelf and segregated. We "
        "request replacement stock and a written response confirming the outcome of your "
        "investigation.", S["body"]))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Vinod Deshpande<br/>Chief Pharmacist, Apollo Pharmacy - Andheri West<br/>"
        "vinod.deshpande@apollopharmacy.example | +91 98201 77340", S["body"]))
    doc.build(story)
    return path


def build_email_complaint():
    """Unstructured email — details buried in prose, no labels to latch onto."""
    path = os.path.join(OUT_DIR, "complaint_cetirizine_email.eml")
    msg = EmailMessage()
    msg["From"] = "Dr. Anita Raghavan <anita.raghavan@medicareclinics.example>"
    msg["To"] = "complaints@aivoa.ai"
    msg["Subject"] = "Urgent - problem with Cetirizine syrup batch, patients affected"
    msg["Date"] = "Mon, 27 Jul 2026 09:14:22 +0530"
    msg.set_content("""\
Dear Sir/Madam,

I am writing on behalf of Medicare Clinics, Pune, regarding a serious issue with a
consignment of your Cetirizine Hydrochloride Oral Solution 5mg/5ml that we received
last month.

Three separate parents have now come to us in the past week saying the syrup tasted
different and that their children refused to take it. When our nursing staff opened
a fresh bottle from the same carton this morning we could immediately see the problem
- the solution has gone slightly cloudy and there is a fine sediment settled at the
bottom of the bottle which does not redisperse even on vigorous shaking. The colour
has also shifted from clear to a faint straw yellow.

The batch on the carton is CTZ26031B, manufactured March 2026, expiry March 2028.
We have 22 bottles of 60ml remaining from this consignment and I have taken all of
them off the shelf this morning. Approximately 14 bottles were dispensed before we
noticed anything, so please advise urgently on what we should tell those families.

One child, a 4 year old, reportedly had loose stools after two doses but I cannot
confirm any connection at this stage and have advised the parents to monitor.

We store all liquid preparations in a temperature controlled room and our logs for
June and July show no excursions above 25 degrees.

Please treat this as urgent given that children are involved. I would like a call
back today if possible.

Regards,
Dr. Anita Raghavan MBBS, DCH
Medicare Clinics, Kothrud, Pune 411038
+91 96570 22841
""")
    with open(path, "wb") as fh:
        fh.write(bytes(msg))
    return path


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for builder in (build_api_complaint, build_fdf_complaint, build_email_complaint):
        print("  ✓", os.path.relpath(builder()))
    print(f"\nSample documents written to {OUT_DIR}")


if __name__ == "__main__":
    main()
