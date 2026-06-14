import json
import os
import re
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent.tax_agent import run_tax_agent
from agent.tools.report_generator import generate_report
from agent.tools.tax_calculator import SUPPORTED_TAX_YEARS

st.set_page_config(
    page_title="TaxIQ Agent",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* ── Sidebar background ─────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f0f7ff 0%, #e8f2fd 100%);
    }

    /* ── Expander cards ─────────────────────────────────────────────── */
    [data-testid="stExpander"] {
        border: 1px solid #c8dff5;
        border-radius: 10px;
        margin-bottom: 8px;
        box-shadow: 0 1px 4px rgba(0,102,204,0.08);
        overflow: hidden;
        background: white;
    }
    [data-testid="stExpander"] details summary {
        background: linear-gradient(135deg, #e6f2ff 0%, #d9ebff 100%);
        color: #003d80 !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
        padding: 10px 14px;
        border-radius: 9px;
        cursor: pointer;
        list-style: none;
        user-select: none;
    }
    [data-testid="stExpander"] details[open] summary {
        border-radius: 9px 9px 0 0;
        border-bottom: 1px solid #c8dff5;
    }
    [data-testid="stExpander"] details summary:hover {
        background: linear-gradient(135deg, #d6e8fc 0%, #c8dffc 100%);
    }
    [data-testid="stExpander"] details summary span {
        color: #003d80 !important;
    }
    [data-testid="stExpander"] details > div {
        padding: 10px 6px 6px 6px;
    }

    /* ── Analyze button ─────────────────────────────────────────────── */
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #0066cc, #0052a3) !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        padding: 12px !important;
        box-shadow: 0 2px 8px rgba(0,102,204,0.35) !important;
        transition: box-shadow 0.2s ease !important;
    }
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
        box-shadow: 0 4px 14px rgba(0,102,204,0.5) !important;
    }

    /* ── Main content cards ─────────────────────────────────────────── */
    .step-box { background:#f0f7ff; border-left:4px solid #0066cc;
                padding:10px 14px; border-radius:4px; margin-bottom:8px; }
    .tool-box { background:#fff8e1; border-left:4px solid #ffa000;
                padding:8px 14px; border-radius:4px; margin-bottom:6px;
                font-family:monospace; font-size:0.85rem; }
    .risk-high  { color:#dc3545; font-weight:600; }
    .risk-med   { color:#fd7e14; font-weight:600; }
    .risk-low   { color:#28a745; font-weight:600; }
    .step-header { background:#e6f2ff; border-left:4px solid #0066cc;
                   padding:8px 14px; border-radius:4px; margin:14px 0 6px 0;
                   font-weight:700; font-size:0.95rem; color:#003d80; }
    .analysis-body ol > li { margin-bottom: 10px; }
    .analysis-body ul > li { margin-bottom: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state init ────────────────────────────────────────────────────────
for key, default in {
    "analysis_done": False,
    "tax_result": {},
    "deductions_result": {},
    "risks_result": {},
    "final_text": "",
    "reasoning_log": "",
    "taxpayer_name": "Acme Digital Media LLC",
    "pdf_path": None,
    "pdf_bytes": None,
    "reasoning_steps": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:4px 0 2px 0">'
        '<span style="font-size:2rem">🧾</span>'
        '<div><div style="font-size:1.3rem;font-weight:800;color:#003d80;line-height:1.1">TaxIQ Agent</div>'
        '<div style="font-size:0.72rem;color:#5588bb;font-weight:500">Powered by Azure AI Foundry</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    with st.expander("🏢  Business Info", expanded=False):
        tax_year = st.selectbox(
            "Tax Year",
            SUPPORTED_TAX_YEARS,
            index=SUPPORTED_TAX_YEARS.index(max(SUPPORTED_TAX_YEARS)),
            format_func=lambda y: f"{y} (Projected)" if y == 2026 else str(y),
        )
        if tax_year == 2026:
            st.warning("2026 brackets are projected (~2.5% CPI). Official figures publish November 2026.", icon="⚠️")
        taxpayer_name = st.text_input("Business / Owner Name", value="Acme Digital Media LLC")
        business_type = st.selectbox(
            "Business Type",
            ["sole_proprietor", "s_corp", "llc", "partnership", "c_corp"],
            index=1,
            format_func=lambda x: x.replace("_", " ").title(),
        )
        filing_status = st.selectbox(
            "Filing Status",
            ["single", "married_filing_jointly", "head_of_household"],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        is_self_employed = st.checkbox("Self-employed / Schedule C", value=True)

    with st.expander("💰  Income", expanded=False):
        gross_income = st.number_input("Gross Revenue ($)", min_value=0, value=280000, step=1000)

    with st.expander("📊  Business Expenses", expanded=False):
        meals = st.number_input("Meals & Entertainment ($)", min_value=0, value=32000, step=100)
        software = st.number_input("Software & Subscriptions ($)", min_value=0, value=9500, step=100)
        advertising = st.number_input("Advertising & Marketing ($)", min_value=0, value=22000, step=100)
        professional_fees = st.number_input("Professional Fees ($)", min_value=0, value=6000, step=100)
        office_supplies = st.number_input("Office Supplies ($)", min_value=0, value=1500, step=100)
        travel = st.number_input("Business Travel ($)", min_value=0, value=28000, step=100)
        insurance = st.number_input("Business Insurance ($)", min_value=0, value=4500, step=100)

    with st.expander("🏠  Special Deductions", expanded=False):
        home_office_sqft = st.number_input("Home Office (sq ft)", min_value=0, value=250, step=10)
        home_total_sqft = st.number_input("Total Home (sq ft)", min_value=0, value=2200, step=10)
        vehicle_miles = st.number_input("Business Miles Driven", min_value=0, value=36000, step=100)

    st.divider()
    analyze_btn = st.button("🔍  Analyze My Taxes", type="primary", use_container_width=True)

# ── Main ──────────────────────────────────────────────────────────────────────
st.title("Tax Readiness Analysis")
st.caption(f"Multi-step AI reasoning · IRS {tax_year} rules · PDF report included")

if analyze_btn:
    # Reset state for new run
    st.session_state.analysis_done = False
    st.session_state.tax_result = {}
    st.session_state.deductions_result = {}
    st.session_state.risks_result = {}
    st.session_state.final_text = ""
    st.session_state.reasoning_log = ""
    st.session_state.taxpayer_name = taxpayer_name
    st.session_state.pdf_path = None
    st.session_state.pdf_bytes = None
    st.session_state.reasoning_steps = []

    expenses = {
        "meals": meals, "software": software, "advertising": advertising,
        "professional_fees": professional_fees, "office_supplies": office_supplies,
        "travel": travel, "insurance": insurance,
    }

    user_prompt = f"""
Please analyze the following tax situation for tax year {tax_year}:

Taxpayer: {taxpayer_name}
Business Type: {business_type}
Filing Status: {filing_status}
Self-Employed: {is_self_employed}
Gross Income: ${gross_income:,}

Expenses: {json.dumps(expenses)}

Home Office: {home_office_sqft} sq ft of {home_total_sqft} sq ft total
Vehicle Business Miles: {vehicle_miles:,}

Please perform your full step-by-step analysis: categorize the financials, identify all deductions using the identify_deductions tool, calculate federal tax liability using calculate_federal_tax, flag any audit risks using flag_audit_risks, and provide recommendations.
"""

    st.subheader("Agent Reasoning Steps")
    progress = st.progress(0, text="Starting analysis...")
    step_count = 0
    tool_count = 0

    for event in run_tax_agent(user_prompt, tax_year=tax_year):
        etype = event["type"]
        content = event["content"]

        if etype == "status":
            st.markdown(f'<div class="step-box">⚙️ {content}</div>', unsafe_allow_html=True)
            st.session_state.reasoning_steps.append({"type": "status", "content": content})
            step_count += 1
            progress.progress(min(step_count * 10, 80), text=content)

        elif etype == "tool_call":
            st.markdown(f'<div class="tool-box">🔧 {content}</div>', unsafe_allow_html=True)
            st.session_state.reasoning_steps.append({"type": "tool_call", "content": content})
            tool_count += 1

        elif etype == "tool_result":
            try:
                parsed = json.loads(content)
                if "total_federal_tax" in parsed:
                    st.session_state.tax_result = parsed
                elif "deductions" in parsed:
                    st.session_state.deductions_result = parsed
                elif "risks" in parsed:
                    st.session_state.risks_result = parsed
                with st.expander(f"Tool result #{tool_count}", expanded=False):
                    st.json(parsed)
            except Exception:
                pass

        elif etype == "error":
            st.error(content)
            st.stop()

        elif etype == "done":
            st.session_state.final_text = content
            st.session_state.reasoning_log = event.get("reasoning_log", "")
            progress.progress(100, text="Analysis complete!")
            st.session_state.analysis_done = True

    # Generate PDF once and store bytes in session state (avoids file I/O on every rerun)
    if st.session_state.analysis_done and st.session_state.tax_result:
        pdf_path = f"taxiq_report_{taxpayer_name.replace(' ', '_')}.pdf"
        generate_report(
            taxpayer_name=taxpayer_name,
            tax_result=st.session_state.tax_result,
            deductions_result=st.session_state.deductions_result,
            risks_result=st.session_state.risks_result,
            agent_reasoning=st.session_state.reasoning_log or st.session_state.final_text,
            output_path=pdf_path,
            tax_year=tax_year,
        )
        st.session_state.pdf_path = pdf_path
        with open(pdf_path, "rb") as f:
            st.session_state.pdf_bytes = f.read()

# ── Results (persisted in session state) ─────────────────────────────────────
if st.session_state.analysis_done:
    # Replay reasoning steps when not in an active run (e.g. after download click)
    if not analyze_btn and st.session_state.reasoning_steps:
        st.subheader("Agent Reasoning Steps")
        for step in st.session_state.reasoning_steps:
            if step["type"] == "status":
                st.markdown(f'<div class="step-box">⚙️ {step["content"]}</div>', unsafe_allow_html=True)
            elif step["type"] == "tool_call":
                st.markdown(f'<div class="tool-box">🔧 {step["content"]}</div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("Analysis Results")

    tax = st.session_state.tax_result
    ded = st.session_state.deductions_result
    risks = st.session_state.risks_result

    if tax:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Federal Tax", f"${tax.get('total_federal_tax', 0):,.0f}")
        with col2:
            st.metric("Effective Rate", f"{tax.get('effective_tax_rate_pct', 0):.1f}%")
        with col3:
            st.metric("Marginal Rate", f"{tax.get('marginal_rate_pct', 0):.1f}%")
        with col4:
            st.metric("Quarterly Est. Payment", f"${tax.get('quarterly_estimated_payment', 0):,.0f}")

        col_a, col_b = st.columns(2, gap="large")
        with col_a:
            breakdown_rows = [
                ("Gross Income", tax.get('gross_income', 0), False, False),
                ("Business Expenses", tax.get('business_expenses_deducted', 0), False, False),
                ("SE Tax Deduction", tax.get('se_tax_deduction', 0), False, False),
                ("QBI Deduction (20%)", tax.get('qbi_deduction', 0), False, False),
                ("Adjusted Gross Income", tax.get('agi', 0), False, False),
                ("Standard Deduction", tax.get('standard_deduction', 0), False, False),
                ("Taxable Income", tax.get('taxable_income', 0), True, False),
                ("Federal Income Tax", tax.get('federal_income_tax', 0), False, False),
                ("Self-Employment Tax", tax.get('self_employment_tax', 0), False, False),
                ("TOTAL FEDERAL TAX", tax.get('total_federal_tax', 0), True, True),
            ]
            table_rows = ""
            for label, val, bold, top_sep in breakdown_rows:
                fw = "700" if bold else "400"
                top_style = "border-top:2px solid #aaa;" if top_sep else ""
                table_rows += (
                    f'<tr style="{top_style}">'
                    f'<td style="padding:5px 4px;border-bottom:1px solid #eee;color:#222;font-weight:{fw}">{label}</td>'
                    f'<td style="padding:5px 4px;border-bottom:1px solid #eee;color:#222;font-weight:{fw};text-align:right;white-space:nowrap">&#36;{int(round(val)):,}</td>'
                    f'</tr>'
                )
            st.markdown(
                f'<p style="font-weight:700;color:#222;margin-bottom:8px">Tax Breakdown</p>'
                f'<table style="width:100%;border-collapse:collapse;font-size:0.88rem">'
                f'{table_rows}</table>',
                unsafe_allow_html=True,
            )

        with col_b:
            if ded:
                total_ded = ded.get('total_deductions', 0)
                ded_rows = ""
                for d in ded.get("deductions", []):
                    code = d['code']
                    cat = d['category']
                    amt = int(round(d['amount']))
                    ded_rows += (
                        f'<tr>'
                        f'<td style="padding:5px 4px;border-bottom:1px solid #eee;color:#222">'
                        f'<span style="font-size:0.72rem;color:#999;margin-right:5px">{code}</span>{cat}'
                        f'</td>'
                        f'<td style="padding:5px 4px;border-bottom:1px solid #eee;color:#222;font-weight:600;text-align:right;white-space:nowrap">&#36;{amt:,}</td>'
                        f'</tr>'
                    )
                total_row = (
                    f'<tr style="border-top:2px solid #aaa;">'
                    f'<td style="padding:5px 4px;color:#222;font-weight:700">TOTAL DEDUCTIONS</td>'
                    f'<td style="padding:5px 4px;color:#222;font-weight:700;text-align:right;white-space:nowrap">&#36;{int(round(total_ded)):,}</td>'
                    f'</tr>'
                )
                st.markdown(
                    f'<p style="font-weight:700;color:#222;margin-bottom:8px">Deductions Found</p>'
                    f'<table style="width:100%;border-collapse:collapse;font-size:0.88rem">'
                    f'{ded_rows}{total_row}</table>',
                    unsafe_allow_html=True,
                )

    if risks:
        st.divider()
        level = risks.get("overall_risk_level", "LOW")
        color = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}.get(level, "green")
        st.markdown(f"**Audit Risk - Overall: :{color}[{level}]**")
        for r in risks.get("risks", []):
            sev = r["severity"]
            css = {"HIGH": "risk-high", "MEDIUM": "risk-med", "LOW": "risk-low"}.get(sev, "risk-low")
            st.markdown(
                f'<span class="{css}">[{sev}]</span> **{r["flag"]}** - {r["detail"]}',
                unsafe_allow_html=True,
            )

    if st.session_state.final_text:
        st.divider()
        st.subheader("Full Agent Analysis")
        # Use full reasoning log (all 5 steps); fall back to final_text if not available
        analysis_text = st.session_state.reasoning_log or st.session_state.final_text
        # Trim any model preamble that appears before [STEP 1:
        step_idx = analysis_text.find('[STEP')
        if step_idx > 0:
            analysis_text = analysis_text[step_idx:]
        # Strip fenced code blocks (JSON tool inputs etc.) — they clutter the narrative
        analysis_text = re.sub(r'```[\w]*\n?[\s\S]*?```', '', analysis_text)
        # Strip inline JSON dicts e.g. {"meals": 3600, ...} that model writes in bullets
        analysis_text = re.sub(r'\{(?:\s*"[^"]+"\s*:\s*[^{}]+,?\s*)+\}', '(see structured data)', analysis_text)
        # Strip LaTeX math \( ... \) and \[ ... \]
        analysis_text = re.sub(r'\\\([\s\S]*?\\\)', '', analysis_text)
        analysis_text = re.sub(r'\\\[[\s\S]*?\\\]', '', analysis_text)
        # Break inline " - Item:" separators onto their own lines (agent sometimes writes items
        # on a single line separated by " - " instead of using newlines)
        analysis_text = re.sub(r'(?<!\n)(?<![0-9]) - (?=[A-Z][^-]{2,}:)', '\n- ', analysis_text)
        # Strip bare ### lines (no text after them)
        analysis_text = re.sub(r'^#{1,6}\s*$', '', analysis_text, flags=re.MULTILINE)
        # Demote markdown headings (##) to bold so they don't render as giant H2/H3
        normalized = re.sub(r'^#{1,6}\s+(.+)$', r'**\1**', analysis_text, flags=re.MULTILINE)
        # Style [STEP N: LABEL] and [STEP N CONTINUED: LABEL] as blue step-header divs
        normalized = re.sub(
            r'\[STEP\s*(\d+)[^:\]]*:\s*([^\]]+)\]',
            lambda m: f'<div class="step-header">Step {m.group(1)}: {m.group(2).strip()}</div>',
            normalized,
        )
        # Style [CONCLUSION ...] and other [ALL CAPS LABEL] headers the same way
        normalized = re.sub(
            r'\[([A-Z][A-Z\s]+)\]',
            lambda m: f'<div class="step-header">{m.group(1).title()}</div>',
            normalized,
        )
        # Add blank line before bold sub-heading lines (**Label:**) for visual breathing room
        normalized = re.sub(r'(?m)^(\*\*[^*\n]+\*\*\s*)$', r'\n\1', normalized)
        # Convert markdown bold/italic to HTML (must run before stripping bare **)
        normalized = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', normalized, flags=re.DOTALL)
        normalized = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', normalized, flags=re.DOTALL)
        normalized = re.sub(r'\*(.+?)\*', r'<em>\1</em>', normalized, flags=re.DOTALL)
        # Strip any leftover bare ** markers (e.g. orphan ** on its own line)
        normalized = re.sub(r'^\*+\s*$', '', normalized, flags=re.MULTILINE)
        normalized = re.sub(r'\*\*', '', normalized)
        # Escape $ before digits — Streamlit treats $...$ as LaTeX math delimiters
        normalized = re.sub(r'\$(\d)', r'&#36;\1', normalized)
        st.markdown(f'<div class="analysis-body">{normalized}</div>', unsafe_allow_html=True)

    # PDF download — bytes stored in session state so reruns (from this click) don't clear results
    if st.session_state.pdf_bytes:
        st.divider()
        st.download_button(
            label="Download Tax Report (PDF)",
            data=st.session_state.pdf_bytes,
            file_name=f"taxiq_report_{st.session_state.taxpayer_name.replace(' ', '_')}.pdf",
            mime="application/pdf",
            type="primary",
        )

    st.caption(
        "This analysis is for informational purposes only and does not constitute "
        "professional tax advice. Always consult a licensed CPA or tax professional."
    )

elif not analyze_btn:
    st.info("Fill in your financial details in the sidebar and click **Analyze My Taxes** to begin.")
