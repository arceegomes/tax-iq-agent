import re
from fpdf import FPDF
from datetime import datetime


def _strip_inline_json(text):
    # Remove inline JSON dict patterns like {"key": 123, ...}
    return re.sub(r'\{(?:\s*"[^"]+"\s*:\s*[^{}]+,?\s*)+\}', '(see structured data)', text)


def _latin1(text):
    text = text.replace('—', '-').replace('–', '-')
    text = text.replace(''', "'").replace(''', "'")
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace('\xd7', 'x')
    return text.encode('latin-1', errors='replace').decode('latin-1')


def _strip_latex(text):
    text = re.sub(r'\\\([\s\S]*?\\\)', '', text)
    text = re.sub(r'\\\[[\s\S]*?\\\]', '', text)
    return text


def _clean(text):
    # Strip fenced code blocks and inline JSON
    text = re.sub(r'```[\w]*\n?[\s\S]*?```', '', text)
    text = _strip_inline_json(text)
    text = _strip_latex(text)
    # Strip bare ### lines and headings
    text = re.sub(r'^#{1,6}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Strip bold/italic markers
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'^\*+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*', '', text)
    # Strip inline code
    text = re.sub(r'`[^`]+`', '', text)
    # Normalise bullet markers
    text = re.sub(r'^\s*[-*]\s+', '  BULLET ', text, flags=re.MULTILINE)
    # Strip horizontal rules
    text = re.sub(r'^\s*-{3,}\s*$', '', text, flags=re.MULTILINE)
    return _latin1(text)


def _clean_plain(text):
    # Like _clean but preserves **...** markers (used by _write_rich before splitting)
    text = re.sub(r'```[\w]*\n?[\s\S]*?```', '', text)
    text = _strip_inline_json(text)
    text = _strip_latex(text)
    text = re.sub(r'^#{1,6}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'^\s*-{3,}\s*$', '', text, flags=re.MULTILINE)
    return _latin1(text)


def _write_rich(pdf, raw_line, line_height=5, is_bullet=False):
    # Render a single line with inline bold support (**label**: value).
    # Strips inline JSON, renders bold label in bold font + rest in regular.
    raw_line = _strip_inline_json(_strip_latex(raw_line))
    # Strip leading bullet marker — is_bullet tracks whether this is a bullet line
    stripped = re.sub(r'^\s*[-*]+\s+', '', raw_line)
    orig_margin = pdf.l_margin

    if is_bullet:
        pdf.set_left_margin(orig_margin + 6)
        pdf.set_x(orig_margin + 6)

    # Use CP1252 bullet character (renders as solid circle with Helvetica)
    prefix = '\x95 ' if is_bullet else ''

    # Detect **label**: rest  OR  **full bold line**
    bold_match = re.match(r'^\s*\*\*([^*]+)\*\*:?\s*(.*)', stripped, re.DOTALL)
    if bold_match:
        label_raw = bold_match.group(1).strip()
        rest_raw  = bold_match.group(2).strip()
        label = _latin1(re.sub(r'\*+', '', label_raw))
        rest  = _latin1(re.sub(r'```[\w]*\n?[\s\S]*?```|`[^`]+`|\*+', '', rest_raw))
        label_str = prefix + label + (': ' if rest else '')
        label_w = pdf.get_string_width(label_str)
        avail   = pdf.w - pdf.l_margin - pdf.r_margin

        if rest and label_w < avail * 0.55:
            # Measure in bold font (same as render font) to avoid width mismatch
            pdf.set_font("Helvetica", "B", 9)
            label_w = pdf.get_string_width(label_str)
            pdf.cell(label_w, line_height, label_str)
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, line_height, rest)
        else:
            pdf.set_font("Helvetica", "B", 9)
            full = (label_str + rest).strip()
            pdf.multi_cell(0, line_height, full)
    else:
        # No bold pattern — strip all markers and render plain
        cleaned = re.sub(r'\*+', '', stripped)
        cleaned = _clean_plain(cleaned).strip()
        # Strip any residual leading bullet markers before adding our own
        cleaned = re.sub(r'^[-*\x95]+\s*', '', cleaned).strip()
        if is_bullet:
            cleaned = '\x95 ' + cleaned
        pdf.set_font("Helvetica", "", 9)
        if cleaned:
            pdf.multi_cell(0, line_height, cleaned)

    if is_bullet:
        pdf.set_left_margin(orig_margin)
        pdf.set_x(orig_margin)


class TaxReport(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_fill_color(0, 102, 204)
        self.set_text_color(255, 255, 255)
        self.cell(0, 12, "TaxIQ Agent - Tax Readiness Report", align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, "This report is for informational purposes only and does not constitute professional tax advice.", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(230, 242, 255)
        self.cell(0, 8, title, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def kv_row(self, label, value, bold_value=False):
        self.set_font("Helvetica", "", 10)
        self.cell(90, 6, label)
        self.set_font("Helvetica", "B" if bold_value else "", 10)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def risk_row(self, flag, severity, detail):
        colors = {"HIGH": (220, 53, 69), "MEDIUM": (255, 153, 0), "LOW": (40, 167, 69)}
        r, g, b = colors.get(severity, (128, 128, 128))
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(r, g, b)
        self.cell(0, 6, "[%s] %s" % (severity, flag), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "I", 9)
        self.multi_cell(0, 5, detail)
        self.ln(1)

    def rec_item(self, number, title, detail):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 6, "%d. %s" % (number, title), new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(60, 60, 60)
        indent = 8
        orig_lmargin = self.l_margin
        self.set_left_margin(orig_lmargin + indent)
        self.set_x(orig_lmargin + indent)
        self.multi_cell(0, 5, detail)
        self.set_left_margin(orig_lmargin)
        self.set_x(orig_lmargin)  # reset X after indent restore
        self.set_text_color(0, 0, 0)
        self.ln(2)


def generate_report(
    taxpayer_name,
    tax_result,
    deductions_result,
    risks_result,
    agent_reasoning,
    output_path="taxiq_report.pdf",
    tax_year=2025,
):
    pdf = TaxReport()
    pdf.add_page()

    # Meta
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Prepared for: %s" % taxpayer_name, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Generated: %s" % datetime.now().strftime('%B %d, %Y'), new_x="LMARGIN", new_y="NEXT")
    if tax_year == 2026:
        pdf.cell(0, 6, "Tax Year: 2026 (Projected - for planning only)", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 6, "Tax Year: %d" % tax_year, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Federal Tax Summary
    pdf.section_title("Federal Tax Summary")
    pdf.kv_row("Gross Income:", "$%s" % "{:,.0f}".format(tax_result.get('gross_income', 0)))
    pdf.kv_row("Business Expenses Deducted:", "$%s" % "{:,.0f}".format(tax_result.get('business_expenses_deducted', 0)))
    pdf.kv_row("SE Tax Deduction:", "$%s" % "{:,.0f}".format(tax_result.get('se_tax_deduction', 0)))
    pdf.kv_row("QBI Deduction (20%):", "$%s" % "{:,.0f}".format(tax_result.get('qbi_deduction', 0)))
    pdf.kv_row("Adjusted Gross Income:", "$%s" % "{:,.0f}".format(tax_result.get('agi', 0)))
    pdf.kv_row("Standard Deduction:", "$%s" % "{:,.0f}".format(tax_result.get('standard_deduction', 0)))
    pdf.kv_row("Taxable Income:", "$%s" % "{:,.0f}".format(tax_result.get('taxable_income', 0)), bold_value=True)
    pdf.ln(2)
    pdf.kv_row("Federal Income Tax:", "$%s" % "{:,.0f}".format(tax_result.get('federal_income_tax', 0)))
    pdf.kv_row("Self-Employment Tax:", "$%s" % "{:,.0f}".format(tax_result.get('self_employment_tax', 0)))
    pdf.kv_row("TOTAL FEDERAL TAX:", "$%s" % "{:,.0f}".format(tax_result.get('total_federal_tax', 0)), bold_value=True)
    pdf.kv_row("Effective Tax Rate:", "%.1f%%" % tax_result.get('effective_tax_rate_pct', 0))
    pdf.kv_row("Marginal Tax Rate:", "%.1f%%" % tax_result.get('marginal_rate_pct', 0))
    pdf.kv_row("Quarterly Estimated Payment:", "$%s" % "{:,.0f}".format(tax_result.get('quarterly_estimated_payment', 0)), bold_value=True)
    pdf.ln(6)

    # Identified Deductions
    pdf.section_title("Identified Deductions")
    for d in deductions_result.get("deductions", []):
        pdf.kv_row("  %s [%s]:" % (d['category'], d['code']), "$%s" % "{:,.0f}".format(d['amount']))
        if d.get("note"):
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 4, "    %s" % _clean(d['note']), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    pdf.kv_row("TOTAL DEDUCTIONS:", "$%s" % "{:,.0f}".format(deductions_result.get('total_deductions', 0)), bold_value=True)
    pdf.ln(6)

    # Audit Risk Assessment
    pdf.section_title("Audit Risk Assessment - Overall: %s" % risks_result.get('overall_risk_level', 'LOW'))
    risks = risks_result.get("risks", [])
    if risks:
        for risk in risks:
            pdf.risk_row(risk["flag"], risk["severity"],
                         risk.get("detail", "") + " " + risk.get("recommendation", ""))
    else:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, "No significant audit risks identified.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Full Agent Reasoning
    if agent_reasoning:
        pdf.add_page()
        pdf.section_title("Full Agent Analysis")
        step_idx = agent_reasoning.find('[STEP')
        text = agent_reasoning[step_idx:] if step_idx >= 0 else agent_reasoning
        # Strip fenced code blocks
        text = re.sub(r'```[\w]*\n?[\s\S]*?```', '', text)
        # Strip markdown table rows (|col|col|) — deductions are already in the structured section
        text = re.sub(r'^[ \t]*\|.*$', '', text, flags=re.MULTILINE)
        # Split on [STEP N: LABEL], [STEP N CONTINUED: LABEL], and [CONCLUSION ...] headers
        parts = re.split(r'(\[STEP\s*\d+[^:\]]*:[^\]]+\]|\[[A-Z][A-Z\s]+\])', text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            step_match = re.match(r'\[STEP\s*(\d+)[^:\]]*:\s*([^\]]+)\]', part)
            label_match = re.match(r'\[([A-Z][A-Z\s]+)\]', part) if not step_match else None
            if step_match or label_match:
                if pdf.get_y() + 30 > pdf.h - pdf.b_margin:
                    pdf.add_page()
                if step_match:
                    label = "Step %s: %s" % (step_match.group(1), step_match.group(2).strip().title())
                else:
                    label = label_match.group(1).title()
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_fill_color(230, 242, 255)
                pdf.cell(0, 7, _clean(label), fill=True, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)
            else:
                pdf.set_text_color(50, 50, 50)
                for line in part.splitlines():
                    line = line.rstrip()
                    if not line:
                        pdf.ln(2)
                        continue
                    # Skip lines that are only whitespace or bare markers after cleaning
                    is_bullet = bool(re.match(r'^\s*[-*]\s+', line))
                    if not re.sub(r'[\s*\-#`]', '', line):
                        continue
                    # Estimate rendered height and start a new page if the line would be split
                    pdf.set_font("Helvetica", "", 9)
                    avail_w = max(1, pdf.w - pdf.l_margin - pdf.r_margin - (6 if is_bullet else 0))
                    est_lines = max(1, int(pdf.get_string_width(_latin1(re.sub(r'\*+', '', line))) / avail_w) + 1)
                    if pdf.get_y() + est_lines * 5 + 4 > pdf.h - pdf.b_margin:
                        pdf.add_page()
                    pdf.set_x(pdf.l_margin)
                    _write_rich(pdf, line, line_height=5, is_bullet=is_bullet)
                pdf.set_text_color(0, 0, 0)
                pdf.ln(1)

    pdf.output(output_path)
    return output_path
