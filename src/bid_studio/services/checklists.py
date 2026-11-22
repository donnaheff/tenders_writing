"""Reporting-guideline checklists (paraphrased summaries).

These are short paraphrases of the CONSORT 2010, PRISMA 2020 and STROBE items so authors can track
what their manuscript reports and where. They are NOT the official checklists: always complete the
official version from the guideline's own website for submission.
"""

from typing import Any

CONSORT = [
    ("1a", "Title and abstract", "Title identifies the study as a randomised trial"),
    ("1b", "Title and abstract", "Structured abstract of design, methods, results and conclusions"),
    ("2a", "Introduction", "Scientific background and rationale"),
    ("2b", "Introduction", "Specific objectives or hypotheses"),
    ("3a", "Methods", "Trial design, including allocation ratio"),
    ("3b", "Methods", "Important changes to methods after the trial started, with reasons"),
    ("4a", "Methods", "Eligibility criteria for participants"),
    ("4b", "Methods", "Settings and locations where data were collected"),
    ("5", "Methods", "The interventions for each group in enough detail to replicate"),
    ("6a", "Methods", "Prespecified primary and secondary outcomes and how and when assessed"),
    ("6b", "Methods", "Any changes to trial outcomes after the trial started, with reasons"),
    ("7a", "Methods", "How the sample size was determined"),
    ("7b", "Methods", "Interim analyses and stopping guidelines, if applicable"),
    ("8a", "Methods", "Method used to generate the random allocation sequence"),
    ("8b", "Methods", "Type of randomisation and any restriction such as blocking"),
    ("9", "Methods", "Mechanism used to implement the allocation sequence and conceal it"),
    ("10", "Methods", "Who generated the sequence, enrolled participants and assigned interventions"),
    ("11a", "Methods", "Who was blinded after assignment, and how"),
    ("11b", "Methods", "If relevant, the similarity of interventions"),
    ("12a", "Methods", "Statistical methods for primary and secondary outcomes"),
    ("12b", "Methods", "Methods for additional analyses such as subgroup and adjusted analyses"),
    ("13a", "Results", "Numbers randomised, receiving treatment and analysed for each group"),
    ("13b", "Results", "Losses and exclusions after randomisation, with reasons"),
    ("14a", "Results", "Dates defining the recruitment and follow-up periods"),
    ("14b", "Results", "Why the trial ended or was stopped"),
    ("15", "Results", "Baseline demographic and clinical characteristics for each group"),
    ("16", "Results", "Number of participants in each analysis and whether by original assignment"),
    ("17a", "Results", "Results for each outcome with effect size and its precision"),
    ("17b", "Results", "For binary outcomes, both absolute and relative effect sizes"),
    ("18", "Results", "Results of any other analyses, distinguishing prespecified from exploratory"),
    ("19", "Results", "All important harms or unintended effects in each group"),
    ("20", "Discussion", "Trial limitations, including sources of bias and imprecision"),
    ("21", "Discussion", "Generalisability (external validity) of the findings"),
    ("22", "Discussion", "Interpretation consistent with results, balancing benefits and harms"),
    ("23", "Other", "Registration number and name of the trial registry"),
    ("24", "Other", "Where the full trial protocol can be accessed"),
    ("25", "Other", "Sources of funding and other support, and the role of funders"),
]

PRISMA = [
    ("1", "Title", "Identify the report as a systematic review"),
    ("2", "Abstract", "Structured abstract following the PRISMA abstract checklist"),
    ("3", "Introduction", "Rationale in the context of existing knowledge"),
    ("4", "Introduction", "Explicit objectives or questions"),
    ("5", "Methods", "Inclusion and exclusion criteria and how studies were grouped"),
    ("6", "Methods", "All databases, registers and other sources searched, with dates"),
    ("7", "Methods", "Full search strategies for every source, with filters and limits"),
    ("8", "Methods", "How records were selected, by how many reviewers, and how disagreements were settled"),
    ("9", "Methods", "How data were collected, by how many people, and any confirmation from authors"),
    ("10a", "Methods", "Outcomes sought and how results were chosen where several were available"),
    ("10b", "Methods", "Other data items sought, such as participants and funding, and assumptions made"),
    ("11", "Methods", "Methods used to assess risk of bias in included studies"),
    ("12", "Methods", "Effect measures used for each outcome"),
    ("13a", "Methods", "How studies were selected for each synthesis"),
    ("13b", "Methods", "Methods to prepare data for synthesis, including missing summary statistics"),
    ("13c", "Methods", "Methods to tabulate or visually display results"),
    ("13d", "Methods", "Methods of synthesis, and the software and models used"),
    ("13e", "Methods", "Methods to explore causes of heterogeneity"),
    ("13f", "Methods", "Sensitivity analyses to test robustness"),
    ("14", "Methods", "Methods to assess risk of bias from missing results"),
    ("15", "Methods", "Methods to assess certainty in the body of evidence"),
    ("16a", "Results", "Search and selection results, ideally with a flow diagram"),
    ("16b", "Results", "Studies that looked eligible but were excluded, with reasons"),
    ("17", "Results", "Characteristics of each included study"),
    ("18", "Results", "Risk of bias assessments for each included study"),
    ("19", "Results", "Summary statistics and effect estimates for each study and outcome"),
    ("20a", "Results", "Characteristics and risk of bias among contributing studies for each synthesis"),
    ("20b", "Results", "Results of all statistical syntheses, with precision and heterogeneity"),
    ("20c", "Results", "Results of investigations into heterogeneity"),
    ("20d", "Results", "Results of sensitivity analyses"),
    ("21", "Results", "Risk of bias due to missing results for each synthesis"),
    ("22", "Results", "Certainty of evidence for each outcome"),
    ("23a", "Discussion", "General interpretation of the results in the context of other evidence"),
    ("23b", "Discussion", "Limitations of the evidence included"),
    ("23c", "Discussion", "Limitations of the review processes used"),
    ("23d", "Discussion", "Implications for practice, policy and future research"),
    ("24a", "Other", "Registration details, or a statement that the review was not registered"),
    ("24b", "Other", "Where the review protocol can be accessed"),
    ("24c", "Other", "Amendments to the registration or protocol"),
    ("25", "Other", "Financial and non-financial support, and the role of funders"),
    ("26", "Other", "Competing interests of the review authors"),
    ("27", "Other", "Availability of template forms, extracted data, analytic code and other materials"),
]

STROBE = [
    ("1a", "Title and abstract", "Study design indicated in the title or abstract"),
    ("1b", "Title and abstract", "Informative and balanced abstract of what was done and found"),
    ("2", "Introduction", "Scientific background and rationale"),
    ("3", "Introduction", "Specific objectives, including prespecified hypotheses"),
    ("4", "Methods", "Key elements of the study design"),
    ("5", "Methods", "Setting, locations and relevant dates, including recruitment and follow-up"),
    ("6", "Methods", "Eligibility criteria, sources and methods of selecting participants"),
    ("7", "Methods", "Outcomes, exposures, predictors, confounders and effect modifiers, with definitions"),
    ("8", "Methods", "Sources of data and methods of assessment for each variable"),
    ("9", "Methods", "Efforts to address potential sources of bias"),
    ("10", "Methods", "How the study size was arrived at"),
    ("11", "Methods", "How quantitative variables were handled in the analyses and why groupings were chosen"),
    ("12a", "Methods", "All statistical methods, including control of confounding"),
    ("12b", "Methods", "Methods used to examine subgroups and interactions"),
    ("12c", "Methods", "How missing data were addressed"),
    ("12d", "Methods", "How loss to follow-up, matching or sampling strategy was addressed, as relevant to the design"),
    ("12e", "Methods", "Any sensitivity analyses"),
    ("13a", "Results", "Numbers of individuals at each stage of the study"),
    ("13b", "Results", "Reasons for non-participation at each stage"),
    ("13c", "Results", "Consider using a flow diagram"),
    ("14a", "Results", "Characteristics of participants and information on exposures and confounders"),
    ("14b", "Results", "Number of participants with missing data for each variable"),
    ("14c", "Results", "For cohort studies, follow-up time"),
    ("15", "Results", "Outcome events or summary measures over time, or exposure categories"),
    ("16a", "Results", "Unadjusted estimates and, if used, confounder-adjusted estimates with precision"),
    ("16b", "Results", "Category boundaries when continuous variables were categorised"),
    ("16c", "Results", "Consider translating relative risk into absolute risk for a meaningful period"),
    ("17", "Results", "Other analyses, such as subgroup, interaction and sensitivity analyses"),
    ("18", "Discussion", "Key results with reference to the study objectives"),
    ("19", "Discussion", "Limitations, including sources of bias and imprecision"),
    ("20", "Discussion", "Cautious overall interpretation considering objectives, limitations and other evidence"),
    ("21", "Discussion", "Generalisability (external validity) of the findings"),
    ("22", "Other", "Source of funding and the role of the funders"),
]

GUIDELINES = {
    "consort_checklist": ("CONSORT 2010 checklist (randomised trials)", CONSORT),
    "prisma_checklist": ("PRISMA 2020 checklist (systematic reviews)", PRISMA),
    "strobe_checklist": ("STROBE checklist (observational studies)", STROBE),
}
REPORTED = ("unchecked", "yes", "no", "na")


def new_items(key: str) -> list[dict[str, Any]]:
    return [
        {"id": f"I{num}", "section": section, "text": text, "reported": "unchecked", "location": "", "notes": ""}
        for num, section, text in GUIDELINES[key][1]
    ]


def export_markdown(title: str, items: list[dict[str, Any]]) -> str:
    out = [f"# {title}", "",
           "_Paraphrased summary for tracking. Complete the official checklist for submission._", "",
           "| Item | Section | Reported | Where | Notes |", "| --- | --- | --- | --- | --- |"]
    for it in items:
        txt = it["text"].replace("|", "\\|")
        out.append(f"| {it['id'][1:]} {txt} | {it['section']} | {it['reported']} | {it['location']} | {it['notes'].replace('|', chr(92) + '|')} |")
    return "\n".join(out) + "\n"
