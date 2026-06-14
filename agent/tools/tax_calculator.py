import json

# ── Per-year IRS data ──────────────────────────────────────────────────────────
_TAX_DATA = {
    2024: {
        "brackets": {
            "single": [
                (11600, 0.10), (47150, 0.12), (100525, 0.22),
                (191950, 0.24), (243725, 0.32), (609350, 0.35), (float("inf"), 0.37),
            ],
            "married_filing_jointly": [
                (23200, 0.10), (94300, 0.12), (201050, 0.22),
                (383900, 0.24), (487450, 0.32), (731200, 0.35), (float("inf"), 0.37),
            ],
            "head_of_household": [
                (16550, 0.10), (63100, 0.12), (100500, 0.22),
                (191950, 0.24), (243700, 0.32), (609350, 0.35), (float("inf"), 0.37),
            ],
        },
        "standard_deduction": {
            "single": 14600,
            "married_filing_jointly": 29200,
            "head_of_household": 21900,
        },
        "se_wage_base": 168600,
        "mileage_rate": 0.67,
        "mileage_code": "Rev. Proc. 2023-34",
    },
    2025: {
        "brackets": {
            "single": [
                (11925, 0.10), (48475, 0.12), (103350, 0.22),
                (197300, 0.24), (250525, 0.32), (626350, 0.35), (float("inf"), 0.37),
            ],
            "married_filing_jointly": [
                (23850, 0.10), (96950, 0.12), (206700, 0.22),
                (394600, 0.24), (501050, 0.32), (751600, 0.35), (float("inf"), 0.37),
            ],
            "head_of_household": [
                (17000, 0.10), (64850, 0.12), (103350, 0.22),
                (197300, 0.24), (250500, 0.32), (626350, 0.35), (float("inf"), 0.37),
            ],
        },
        "standard_deduction": {
            "single": 15000,
            "married_filing_jointly": 30000,
            "head_of_household": 22500,
        },
        "se_wage_base": 176100,
        "mileage_rate": 0.70,
        "mileage_code": "Rev. Proc. 2024-25",
    },
    # 2026 figures are projected based on ~2.5% CPI inflation adjustment from 2025.
    # IRS publishes official brackets in November each year.
    2026: {
        "brackets": {
            "single": [
                (12200, 0.10), (49700, 0.12), (105900, 0.22),
                (202200, 0.24), (256800, 0.32), (641900, 0.35), (float("inf"), 0.37),
            ],
            "married_filing_jointly": [
                (24400, 0.10), (99350, 0.12), (211850, 0.22),
                (404450, 0.24), (513600, 0.32), (770200, 0.35), (float("inf"), 0.37),
            ],
            "head_of_household": [
                (17400, 0.10), (66450, 0.12), (105900, 0.22),
                (202200, 0.24), (256750, 0.32), (641900, 0.35), (float("inf"), 0.37),
            ],
        },
        "standard_deduction": {
            "single": 15350,
            "married_filing_jointly": 30700,
            "head_of_household": 23100,
        },
        "se_wage_base": 181900,
        "mileage_rate": 0.70,
        "mileage_code": "Projected",
        "projected": True,
    },
}

SUPPORTED_TAX_YEARS = sorted(_TAX_DATA.keys())


def _year_data(tax_year: int) -> dict:
    return _TAX_DATA.get(tax_year, _TAX_DATA[max(_TAX_DATA)])


def calculate_federal_tax(
    gross_income: float,
    filing_status: str,
    business_expenses: float,
    is_self_employed: bool,
    additional_deductions: float = 0,
    tax_year: int = 2025,
) -> str:
    data = _year_data(tax_year)
    filing_status = filing_status.lower().replace(" ", "_")
    brackets = data["brackets"].get(filing_status, data["brackets"]["single"])
    std_deduction = data["standard_deduction"].get(filing_status, data["standard_deduction"]["single"])
    se_wage_base = data["se_wage_base"]

    se_tax = 0.0
    se_deduction = 0.0
    net_se_income = max(0, gross_income - business_expenses)
    if is_self_employed and net_se_income > 0:
        se_base = min(net_se_income * 0.9235, se_wage_base)
        se_tax = se_base * 0.153
        se_deduction = se_tax / 2

    qbi_deduction = max(0, net_se_income - se_deduction) * 0.20 if is_self_employed else 0
    agi = gross_income - business_expenses - se_deduction - additional_deductions
    taxable_income = max(0, agi - std_deduction - qbi_deduction)

    income_tax = 0.0
    marginal_rate = 0.0
    prev_bracket = 0
    for ceiling, rate in brackets:
        if taxable_income <= prev_bracket:
            break
        taxable_in_bracket = min(taxable_income, ceiling) - prev_bracket
        income_tax += taxable_in_bracket * rate
        if taxable_income <= ceiling:
            marginal_rate = rate
            break
        prev_bracket = ceiling

    total_tax = income_tax + se_tax
    effective_rate = (total_tax / gross_income * 100) if gross_income > 0 else 0

    return json.dumps({
        "tax_year": tax_year,
        "gross_income": round(gross_income, 2),
        "business_expenses_deducted": round(business_expenses, 2),
        "se_tax_deduction": round(se_deduction, 2),
        "qbi_deduction": round(qbi_deduction, 2),
        "agi": round(agi, 2),
        "standard_deduction": std_deduction,
        "taxable_income": round(taxable_income, 2),
        "federal_income_tax": round(income_tax, 2),
        "self_employment_tax": round(se_tax, 2),
        "total_federal_tax": round(total_tax, 2),
        "effective_tax_rate_pct": round(effective_rate, 2),
        "marginal_rate_pct": round(marginal_rate * 100, 1),
        "quarterly_estimated_payment": round(total_tax / 4, 2),
    })


def identify_deductions(
    expenses: dict = None,
    business_type: str = "sole_proprietor",
    home_office_sqft: int = 0,
    home_total_sqft: int = 0,
    vehicle_business_miles: int = 0,
    tax_year: int = 2025,
) -> str:
    data = _year_data(tax_year)
    if expenses is None:
        expenses = {}
    deductions = []
    total = 0.0

    deductible_categories = {
        "advertising": ("Advertising & Marketing", "IRC §162"),
        "software": ("Software & Subscriptions", "IRC §162 / §179"),
        "office_supplies": ("Office Supplies", "IRC §162"),
        "professional_fees": ("Professional & Legal Fees", "IRC §162"),
        "insurance": ("Business Insurance", "IRC §162"),
        "travel": ("Business Travel", "IRC §162"),
        "utilities": ("Business Utilities", "IRC §162"),
        "wages": ("Employee Wages", "IRC §162"),
        "rent": ("Office/Equipment Rent", "IRC §162"),
        "education": ("Business Education & Training", "IRC §162"),
    }

    for key, (label, code) in deductible_categories.items():
        amount = expenses.get(key, 0)
        if amount > 0:
            deductions.append({"category": label, "amount": round(amount, 2), "code": code})
            total += amount

    meals = expenses.get("meals", 0)
    if meals > 0:
        allowed = meals * 0.50
        deductions.append({
            "category": "Meals (50% of total)",
            "amount": round(allowed, 2),
            "code": "IRC §274",
            "note": f"50% of ${meals:,.0f} total meals expense",
        })
        total += allowed

    if home_office_sqft > 0 and home_total_sqft > 0:
        simplified = min(home_office_sqft, 300) * 5
        deductions.append({
            "category": "Home Office (Simplified Method)",
            "amount": round(simplified, 2),
            "code": "IRC §280A",
            "note": f"{min(home_office_sqft, 300)} sqft x $5",
        })
        total += simplified

    if vehicle_business_miles > 0:
        rate = data["mileage_rate"]
        code = data["mileage_code"]
        mileage_deduction = vehicle_business_miles * rate
        deductions.append({
            "category": "Vehicle (Standard Mileage)",
            "amount": round(mileage_deduction, 2),
            "code": code,
            "note": f"{vehicle_business_miles:,} miles x ${rate}",
        })
        total += mileage_deduction

    return json.dumps({
        "tax_year": tax_year,
        "business_type": business_type,
        "deductions": deductions,
        "total_deductions": round(total, 2),
    })


def flag_audit_risks(
    gross_income: float,
    expenses: dict = None,
    home_office_sqft: int = 0,
    vehicle_business_miles: int = 0,
    tax_year: int = 2025,
) -> str:
    if expenses is None:
        expenses = {}
    risks = []

    total_expenses = sum(expenses.values())
    expense_ratio = (total_expenses / gross_income) if gross_income > 0 else 0

    if expense_ratio > 0.85:
        risks.append({
            "flag": "Very high expense-to-income ratio",
            "severity": "HIGH",
            "detail": f"Expenses are {expense_ratio*100:.0f}% of gross income. IRS may scrutinize deductions.",
            "recommendation": "Ensure all expenses are fully documented with receipts.",
        })
    elif expense_ratio > 0.70:
        risks.append({
            "flag": "Elevated expense-to-income ratio",
            "severity": "MEDIUM",
            "detail": f"Expenses are {expense_ratio*100:.0f}% of gross income.",
            "recommendation": "Retain all supporting documentation.",
        })

    meals = expenses.get("meals", 0)
    if meals > 0 and (meals / gross_income) > 0.10:
        risks.append({
            "flag": "Meals deduction exceeds 10% of income",
            "severity": "MEDIUM",
            "detail": "Large meals deductions relative to income are an audit trigger.",
            "recommendation": "Document business purpose and attendees for every meal.",
        })

    if vehicle_business_miles > 30000:
        risks.append({
            "flag": "High vehicle business mileage",
            "severity": "MEDIUM",
            "detail": f"{vehicle_business_miles:,} business miles claimed.",
            "recommendation": "Maintain a contemporaneous mileage log (IRS Form 4562).",
        })

    if home_office_sqft > 200:
        risks.append({
            "flag": "Large home office deduction",
            "severity": "LOW",
            "detail": f"{home_office_sqft} sqft home office claimed.",
            "recommendation": "Space must be used regularly and exclusively for business.",
        })

    if gross_income > 200000 and expenses.get("wages", 0) == 0:
        risks.append({
            "flag": "High revenue S-Corp with no wages",
            "severity": "HIGH",
            "detail": "IRS requires S-Corp owners to pay reasonable compensation.",
            "recommendation": "Consult a CPA about setting a reasonable salary.",
        })

    return json.dumps({
        "tax_year": tax_year,
        "risk_count": len(risks),
        "risks": risks,
        "overall_risk_level": "HIGH" if any(r["severity"] == "HIGH" for r in risks)
        else "MEDIUM" if any(r["severity"] == "MEDIUM" for r in risks)
        else "LOW",
    })


# Tool schemas — tax_year injected server-side, not exposed to model
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_federal_tax",
            "description": "Calculate estimated federal income tax and self-employment tax given financial inputs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gross_income": {"type": "number", "description": "Total gross income in USD"},
                    "filing_status": {
                        "type": "string",
                        "enum": ["single", "married_filing_jointly", "head_of_household"],
                    },
                    "business_expenses": {"type": "number", "description": "Total deductible business expenses"},
                    "is_self_employed": {"type": "boolean"},
                    "additional_deductions": {"type": "number", "default": 0},
                },
                "required": ["gross_income", "filing_status", "business_expenses", "is_self_employed"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "identify_deductions",
            "description": "Identify all applicable IRS deductions from business expense data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expenses": {"type": "object", "description": "Dict of expense category to dollar amount"},
                    "business_type": {
                        "type": "string",
                        "enum": ["sole_proprietor", "s_corp", "llc", "partnership", "c_corp"],
                    },
                    "home_office_sqft": {"type": "integer", "default": 0},
                    "home_total_sqft": {"type": "integer", "default": 0},
                    "vehicle_business_miles": {"type": "integer", "default": 0},
                },
                "required": ["expenses", "business_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_audit_risks",
            "description": "Flag potential IRS audit risk items in the tax return.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gross_income": {"type": "number"},
                    "expenses": {"type": "object"},
                    "home_office_sqft": {"type": "integer", "default": 0},
                    "vehicle_business_miles": {"type": "integer", "default": 0},
                },
                "required": ["gross_income", "expenses"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "calculate_federal_tax": calculate_federal_tax,
    "identify_deductions": identify_deductions,
    "flag_audit_risks": flag_audit_risks,
}
