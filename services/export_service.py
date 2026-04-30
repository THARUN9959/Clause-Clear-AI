"""
ClauseClear AI — PDF Export Service using fpdf2.

Generates a structured PDF report for a completed contract analysis.
Uses ONLY fpdf2 — no weasyprint, pdfkit, or wkhtmltopdf.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from fpdf import FPDF
    _FPDF_AVAILABLE = True
except ImportError:
    _FPDF_AVAILABLE = False
    logger.warning("fpdf2 not installed — PDF export will not be available. Run: pip install fpdf2")


class _ContractPDF(FPDF):
    """Custom PDF class with header and footer."""

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(15, 23, 42)
        self.set_text_color(255, 255, 255)
        self.rect(0, 0, 210, 14, "F")
        self.set_y(3)
        self.cell(0, 8, "ClauseClear AI  -  Contract Analysis Report", align="C")
        self.set_text_color(0, 0, 0)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(
            0, 10,
            "This analysis is AI-generated and does not constitute legal advice.  "
            f"Generated {datetime.now().strftime('%Y-%m-%d')}  |  Page {self.page_no()}",
            align="C",
        )


def _safe_str(val) -> str:
    """Convert any value to a safe ASCII-compatible string for fpdf."""
    if val is None:
        return "N/A"
    text = str(val)
    # Replace common unicode chars that FPDF core fonts can't render
    replacements = {
        "\u2013": "-", "\u2014": "--", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2022": "*", "\u2026": "...",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _severity_color(severity: str) -> tuple:
    """Return (R,G,B) for a severity level."""
    return {
        "HIGH": (239, 68, 68),
        "MEDIUM": (249, 115, 22),
        "LOW": (234, 179, 8),
    }.get(severity.upper(), (100, 100, 100))


def generate_pdf(analysis_row) -> bytes:
    """
    Generate a PDF report from an AnalysisModel row.

    Args:
        analysis_row: An AnalysisModel ORM instance.

    Returns:
        PDF file as bytes.
    """
    if not _FPDF_AVAILABLE:
        raise RuntimeError("fpdf2 is not installed. Run: pip install fpdf2")

    try:
        data = json.loads(analysis_row.analysis_json)
    except (json.JSONDecodeError, TypeError):
        data = {}

    pdf = _ContractPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_margins(15, 20, 15)

    # ── Title block ────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 10, _safe_str(analysis_row.filename), ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, f"Contract Type: {_safe_str(analysis_row.contract_type)}", ln=True)
    pdf.cell(0, 6, f"Analyzed: {analysis_row.created_at.strftime('%Y-%m-%d %H:%M UTC')}", ln=True)
    pdf.ln(4)

    # ── Health score ───────────────────────────────────────────
    score = analysis_row.health_score
    grade = _safe_str(data.get("health_grade", "?"))
    verdict = _safe_str(data.get("health_verdict", ""))

    grade_colors = {
        "A": (22, 163, 74), "B": (20, 184, 166),
        "C": (234, 179, 8), "D": (249, 115, 22), "F": (239, 68, 68),
    }
    r, g, b = grade_colors.get(grade, (100, 100, 100))

    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(50, 12, f"Score: {score}/100  Grade: {grade}", fill=True, ln=False)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 12, f"  {verdict}", ln=True)
    pdf.ln(4)

    # ── Summary ────────────────────────────────────────────────
    summary = _safe_str(data.get("summary", "No summary available."))
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 8, "Contract Summary", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(0, 6, summary)
    pdf.ln(6)

    # ── Key Entities ────────────────────────────────────────────
    key_entities = data.get("key_entities", {})
    if key_entities:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 8, "Key Entities", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50, 50, 50)
        parties = ", ".join(key_entities.get("parties", [])) or "N/A"
        pdf.cell(0, 6, f"Parties: {_safe_str(parties)}", ln=True)
        pdf.cell(0, 6, f"Effective Date: {_safe_str(key_entities.get('effective_date', 'N/A'))}", ln=True)
        pdf.cell(0, 6, f"Governing Law: {_safe_str(key_entities.get('governing_law', 'N/A'))}", ln=True)
        pdf.cell(0, 6, f"Termination Notice: {_safe_str(key_entities.get('termination_notice', 'N/A'))}", ln=True)
        pdf.ln(6)

    # ── Risks table ────────────────────────────────────────────
    risks = data.get("risks", [])
    if risks:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 8, f"Risk Analysis ({len(risks)} risks identified)", ln=True)

        # Table header
        pdf.set_fill_color(240, 240, 245)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(45, 7, "Clause", border=1, fill=True)
        pdf.cell(22, 7, "Severity", border=1, fill=True)
        pdf.cell(123, 7, "Explanation", border=1, fill=True, ln=True)

        pdf.set_font("Helvetica", "", 9)
        for risk in risks:
            sev = _safe_str(risk.get("severity", "LOW")).upper()
            r2, g2, b2 = _severity_color(sev)
            clause = _safe_str(risk.get("clause", "Unknown"))[:40]
            explanation = _safe_str(risk.get("explanation", ""))[:200]

            # Row height varies with explanation length — use multi_cell trick
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.cell(45, 7, clause, border=1)
            pdf.set_text_color(r2, g2, b2)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(22, 7, sev, border=1)
            pdf.set_text_color(50, 50, 50)
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(123, 7, explanation, border=1)

            # Suggested redline
            redline = _safe_str(risk.get("suggested_redline", ""))
            if redline:
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(80, 80, 160)
                pdf.cell(67, 6, "", border=0)
                pdf.multi_cell(123, 6, f"Suggested: {redline[:150]}")
                pdf.set_text_color(50, 50, 50)

            # Legal Standard
            sj = _safe_str(risk.get("standard_justification", ""))
            if sj and sj != "N/A":
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(22, 163, 74)
                pdf.cell(67, 6, "", border=0)
                pdf.multi_cell(123, 6, f"Legal Standard: {sj[:200]}")
                pdf.set_text_color(50, 50, 50)

        pdf.ln(6)

    # ── Obligations table ──────────────────────────────────────
    obligations = data.get("obligations", [])
    if obligations:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 8, f"Obligations & Deadlines ({len(obligations)} items)", ln=True)

        pdf.set_fill_color(240, 240, 245)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(10, 7, "#", border=1, fill=True)
        pdf.cell(70, 7, "Obligation", border=1, fill=True)
        pdf.cell(40, 7, "Party", border=1, fill=True)
        pdf.cell(45, 7, "Deadline", border=1, fill=True)
        pdf.cell(25, 7, "Section", border=1, fill=True, ln=True)

        pdf.set_font("Helvetica", "", 9)
        for i, obl in enumerate(obligations, 1):
            pdf.cell(10, 7, str(i), border=1)
            pdf.cell(70, 7, _safe_str(obl.get("obligation", ""))[:55], border=1)
            pdf.cell(40, 7, _safe_str(obl.get("party", ""))[:32], border=1)
            pdf.cell(45, 7, _safe_str(obl.get("deadline_description", ""))[:35], border=1)
            pdf.cell(25, 7, _safe_str(obl.get("section", ""))[:18], border=1, ln=True)

    return pdf.output()
