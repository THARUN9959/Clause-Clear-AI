"""
ClauseClear AI — Benchmark Service.

Provides market-standard reference data for each contract type.
Injected into Gemini analysis prompts so that risk explanations
explicitly compare against real-world norms.
"""


def get_benchmark_context(contract_type: str) -> dict:
    """
    Return a dict of market-standard ranges for the given contract type.
    Keys are clause areas, values are human-readable benchmark strings.
    """
    _BENCHMARKS = {
        "NDA": {
            "duration": "Market standard: 2–3 years. Perpetual NDAs are non-standard and aggressive.",
            "scope": "Market standard: confidential information exchanged for the specific project/relationship only. Blanket 'all information' scopes are aggressive.",
            "mutual_vs_unilateral": "Mutual NDAs are preferred; unilateral NDAs heavily favour the disclosing party.",
            "residuals_clause": "Residuals clauses allow retained knowledge to be used freely — a significant risk for trade secrets.",
            "jurisdiction": "Jurisdiction should be the state/country where both parties primarily operate.",
            "ip_assignment": "IP assignment should be limited to work product created under the agreement, not pre-existing IP.",
        },
        "EMPLOYMENT": {
            "non_compete_duration": "Market standard: 6–12 months post-employment. Over 18 months is aggressive; over 24 months is often unenforceable.",
            "non_compete_geography": "Market standard: limited to regions where the employer actively operates. Nationwide or global scope is aggressive.",
            "equity_vesting": "Market standard: 4-year vesting with a 1-year cliff. Shorter cliffs favour the employee.",
            "ip_assignment": "Market standard: covers work created during work hours or using company resources. Side projects on personal time/equipment should be excluded.",
            "arbitration": "Mandatory arbitration waivers limit employees' court access — standard in US tech but controversial.",
            "at_will": "At-will employment is standard in the US; fixed-term contracts offer more job security.",
            "severance": "Market standard for executives: 3–6 months. Standard employees: 2–4 weeks per year of service.",
        },
        "SAAS_TOS": {
            "auto_renewal_notice": "Market standard: 30–60 days notice required to cancel before auto-renewal. Under 15 days is a red flag.",
            "liability_cap": "Market standard: fees paid in the last 12 months. Caps below 3 months are aggressive.",
            "data_ownership": "Customer data should remain owned by the customer. Vendor claiming ownership of customer data is a major red flag.",
            "sla_uptime": "Market standard SaaS SLA: 99.9% uptime (allowing ~8.7 hours/year downtime). Below 99% is weak.",
            "unilateral_modification": "Vendors should provide at least 30 days notice before materially changing terms.",
            "data_retention": "Market standard: customer data returned or destroyed within 30–60 days of contract termination.",
        },
        "FREELANCE": {
            "payment_terms": "Market standard: Net-30. Beyond Net-60 is unusual and increases cash flow risk.",
            "kill_fee": "Market standard: 25–50% of project value if client cancels after work begins.",
            "ip_transfer": "IP should transfer only upon full payment. Work-for-hire before payment is risky for the freelancer.",
            "revision_limits": "Market standard: 2–3 rounds of revisions included. Unlimited revisions favour the client.",
            "non_solicit": "Non-solicit clauses should be limited to 12 months and specific client contacts, not entire industries.",
            "indemnification": "One-sided indemnification clauses heavily favouring the client are a red flag.",
        },
        "RENTAL": {
            "security_deposit": "Market standard: 1–2 months rent. Over 3 months is aggressive in most jurisdictions.",
            "notice_period": "Market standard for month-to-month: 30 days notice by either party. Some jurisdictions require 60 days.",
            "early_termination": "Early termination penalties beyond 2 months rent are aggressive.",
            "maintenance": "Landlord is typically responsible for structural repairs; tenant for minor maintenance.",
            "subletting": "Total subletting prohibition limits tenant flexibility beyond market norms.",
            "rent_increase": "Market standard: annual rent increase tied to CPI (inflation). Uncapped increases are aggressive.",
        },
        "LOAN": {
            "interest_rate": "Market standard for personal loans: 6–12% APR. Above 20% APR approaches predatory territory.",
            "prepayment_penalty": "Market standard: no prepayment penalty. Any prepayment penalty above 2% is aggressive.",
            "default_cure_period": "Market standard: 10–30 days cure period before default acceleration. Less than 5 days is aggressive.",
            "collateral": "Collateral should be proportional to loan value. Blanket liens on all assets are aggressive.",
        },
        "PARTNERSHIP": {
            "profit_distribution": "Should be clearly defined and tied to contribution/equity percentage.",
            "decision_making": "Deadlock resolution mechanisms are essential for equal partnerships.",
            "dissolution": "Exit provisions and buyout formulas should be pre-agreed to avoid disputes.",
            "non_compete": "Partner non-competes post-dissolution: market standard 12–24 months, limited geography.",
            "ip_ownership": "IP created by partners for the partnership should be clearly assigned to the partnership entity.",
        },
        "UNKNOWN": {
            "general": "Without a specific contract type, applying balanced general legal analysis standards.",
            "liability": "Liability caps should be proportional to contract value.",
            "termination": "Either party should have a reasonable notice period (30 days minimum) to terminate.",
            "dispute_resolution": "Arbitration vs. litigation should be clearly specified with jurisdiction.",
        },
    }

    return _BENCHMARKS.get(contract_type, _BENCHMARKS["UNKNOWN"])


def format_benchmark_for_prompt(contract_type: str) -> str:
    """
    Format benchmark context as a string block for injection into Gemini prompts.
    """
    benchmarks = get_benchmark_context(contract_type)
    lines = [f"=== MARKET BENCHMARK STANDARDS FOR {contract_type} CONTRACTS ==="]
    lines.append("Use these benchmarks explicitly when explaining each risk. Compare clause terms against these norms.")
    for area, standard in benchmarks.items():
        lines.append(f"• {area.replace('_', ' ').title()}: {standard}")
    return "\n".join(lines)
