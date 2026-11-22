"""Document packs: a bundle of related documents created together."""

PACKS: dict[str, dict] = {
    "iso27001_starter": {
        "title": "ISO 27001 starter pack",
        "description": "Core policies, statement of applicability, internal audit and management review.",
        "types": ["infosec_policy", "data_protection_policy", "incident_response_plan", "bcp_dr_plan",
                  "soa", "internal_audit_report", "management_review"],
    },
    "privacy_pack": {
        "title": "Privacy compliance pack",
        "description": "Privacy notice, records of processing, DPIA and data protection policy.",
        "types": ["privacy_notice", "ropa", "dpia", "data_protection_policy"],
    },
    "funder_reporting": {
        "title": "Funder reporting pack",
        "description": "Progress report, final report, lay summary and sustainability plan. Link a proposal to pre-fill.",
        "types": ["funder_progress_report", "funder_final_report", "lay_summary", "sustainability_plan"],
    },
    "tender_response": {
        "title": "Tender response pack",
        "description": "Method statement, mobilisation, exit plan, RAMS, quality manual, CVs and case study.",
        "types": ["method_statement", "mobilisation_plan", "exit_plan", "rams", "quality_manual",
                  "team_cv", "case_study", "capability_statement"],
    },
    "saas_documentation": {
        "title": "SaaS product documentation pack",
        "description": "README, user guide, API reference, integration guide, release notes, runbook and help article.",
        "types": ["readme_onboarding", "user_guide", "api_reference", "integration_guide", "release_notes",
                  "runbook", "kb_article"],
    },
    "engineering_ops": {
        "title": "Engineering and operations pack",
        "description": "Runbook, incident report, ADR, test plan, test cases, data dictionary and migration guide.",
        "types": ["runbook", "incident_report", "adr", "test_plan", "test_cases", "data_dictionary", "migration_guide"],
    },
    "ai_governance": {
        "title": "AI governance pack",
        "description": "Model card, dataset datasheet, AI impact assessment, EU AI Act outline and DPIA.",
        "types": ["model_card", "dataset_datasheet", "ai_impact_assessment", "ai_act_tech_doc", "dpia"],
    },
    "product_launch": {
        "title": "Product launch pack",
        "description": "PRD, business case, feasibility study and competitive analysis.",
        "types": ["prd", "business_case", "feasibility_study", "competitive_analysis"],
    },
    "hardware_release": {
        "title": "Hardware release pack",
        "description": "Installation guide, maintenance manual, datasheet and test report.",
        "types": ["installation_manual", "maintenance_manual", "product_datasheet", "test_report"],
    },
    "research_submission": {
        "title": "Research submission pack",
        "description": "Manuscript, cover letter to the editor and conference abstract.",
        "types": ["research_manuscript", "journal_cover_letter", "conference_abstract"],
    },
}


def catalogue(types: dict) -> list[dict]:
    return [{"key": k, "title": v["title"], "description": v["description"],
             "documents": [{"key": t, "title": types[t]["title"]} for t in v["types"]]} for k, v in PACKS.items()]
