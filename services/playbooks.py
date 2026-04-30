"""
ClauseClear AI - Indian Legal Playbooks

This module defines the explicit legal standards used to ground the Gemini AI's 
risk evaluations. This ensures the AI does not hallucinate arbitrary risks and 
strictly applies Indian statutory frameworks (e.g., Indian Contract Act 1872, DPDP Act 2023).
"""

PLAYBOOKS = {
    "general_commercial": """
    Evaluate this contract strictly under Indian law.
    Apply the Indian Contract Act, 1872 as the primary framework.
    Flag any penalty or liquidated damages clauses and cite Section 74
    of the Indian Contract Act (penalties must be a genuine pre-estimate
    of loss, not a punishment). Flag agreements in restraint of trade
    under Section 27. Flag contracts with minors under Section 11.
    Flag any arbitration clause and note whether it aligns with the
    Arbitration and Conciliation Act, 1996. For every HIGH risk clause,
    provide a standard_justification citing the specific Indian statute
    and section number.
    """,

    "data_privacy_tech": """
    Evaluate this contract strictly under Indian data protection law.
    Apply the Digital Personal Data Protection (DPDP) Act, 2023 and the
    Information Technology Act, 2000 as the primary frameworks.
    Flag any data processing clause that lacks clear, free, and informed
    consent of the data principal as HIGH_RISK under DPDP Act Section 6.
    Flag absence of data breach notification obligations as HIGH_RISK
    under DPDP Act Section 8(6). Flag any transfer of personal data to
    countries not notified by the central government as HIGH_RISK under
    DPDP Act Section 16. Flag vague or overly broad data retention clauses.
    Flag any clause that prevents the data principal from exercising their
    rights (erasure, correction, grievance redressal) under DPDP Act
    Sections 12-13. For every HIGH risk clause, provide a
    standard_justification citing the specific DPDP or IT Act section.
    """,

    "pro_vendor": """
    Evaluate this contract from the perspective of a vendor or service
    provider operating under Indian law. Identify clauses that are
    unfavorable to the vendor. Flag unlimited liability clauses as
    HIGH_RISK (suggest capping at 3-6 months of contract value as per
    Indian market standard). Flag unilateral termination rights given
    to the client without a cure period as HIGH_RISK. Flag IP ownership
    clauses that assign all work product to the client without carving
    out pre-existing IP. Flag payment terms exceeding Net-45 as RISK.
    Flag non-compete clauses broader than 12 months or without geographic
    limits as HIGH_RISK. Evaluate under the Indian Contract Act, 1872
    for enforceability. For every HIGH risk clause, provide a
    standard_justification from the vendor's perspective.
    """,

    "pro_buyer": """
    Evaluate this contract from the perspective of a buyer or client
    operating under Indian law. Identify clauses that are unfavorable
    to the buyer. Flag absence of SLA or performance guarantees as
    HIGH_RISK. Flag limitation of liability clauses that cap vendor
    liability below 12 months of contract value as HIGH_RISK. Flag
    auto-renewal clauses without advance written notice to buyer as
    HIGH_RISK. Flag broad indemnification clauses that shift all risk
    to the buyer. Flag IP clauses where the vendor retains ownership
    of custom-built work. Evaluate under the Indian Contract Act, 1872.
    For every HIGH risk clause, provide a standard_justification from
    the buyer's perspective.
    """
}

PLAYBOOK_LABELS = {
    "general_commercial": "General Commercial (Indian Contract Act, 1872)",
    "data_privacy_tech":  "Data Privacy & Tech (DPDP Act, 2023 & IT Act, 2000)",
    "pro_vendor":         "Pro-Vendor / Service Provider (Indian standard)",
    "pro_buyer":          "Pro-Buyer / Client (Indian standard)",
}

DEFAULT_STANDARD = "general_commercial"
