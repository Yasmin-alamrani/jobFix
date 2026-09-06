"""Industry context packs.

These steer the model toward the vocabulary and credentials a given sector's
screeners actually look for. Saudi-relevant regulators are included where they
matter (SAMA for banking and fintech, CMA for capital markets, SOCPA for
accounting) because a candidate who names them reads as local to the market.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IndustryPack:
    key: str
    label: str
    tone: str
    certifications: list[str] = field(default_factory=list)
    emphasis: list[str] = field(default_factory=list)


PACKS: dict[str, IndustryPack] = {
    "tech": IndustryPack(
        key="tech", label="Technology",
        tone="Direct and metric-led. Impact and scale over responsibilities.",
        certifications=["AWS Certified Solutions Architect", "Certified Kubernetes Administrator (CKA)"],
        emphasis=["systems designed and their scale", "languages and frameworks",
                  "ownership and on-call", "measurable performance or reliability gains"],
    ),
    "banking": IndustryPack(
        key="banking", label="Banking",
        tone="Formal and precise. Risk, controls and regulatory exposure matter.",
        certifications=["Chartered Financial Analyst (CFA)",
                        "Financial Risk Manager (FRM)",
                        "Saudi Organization for Chartered and Professional Accountants (SOCPA)"],
        emphasis=["regulatory frameworks (SAMA, Basel)", "risk and controls",
                  "portfolio or transaction size", "audit and compliance record"],
    ),
    "fintech": IndustryPack(
        key="fintech", label="Fintech",
        tone="Blend of engineering impact and regulatory literacy.",
        certifications=["Certified Information Systems Security Professional (CISSP)",
                        "Project Management Professional (PMP)"],
        emphasis=["payments rails and settlement", "SAMA licensing and sandbox exposure",
                  "KYC/AML systems", "transaction volume handled"],
    ),
    "energy": IndustryPack(
        key="energy", label="Energy",
        tone="Formal. Safety record and project scale lead.",
        certifications=["Project Management Professional (PMP)",
                        "NEBOSH International General Certificate"],
        emphasis=["project value and duration", "HSE record", "upstream/downstream exposure"],
    ),
    "healthcare": IndustryPack(
        key="healthcare", label="Healthcare",
        tone="Formal and credential-forward.",
        certifications=["Saudi Commission for Health Specialties (SCFHS) registration"],
        emphasis=["licensure and registration", "clinical specialisation", "patient volume"],
    ),
    "consulting": IndustryPack(
        key="consulting", label="Consulting",
        tone="Structured and outcome-led. Quantified client impact throughout.",
        certifications=["Project Management Professional (PMP)"],
        emphasis=["client outcomes in numbers", "industries served", "team leadership"],
    ),
    "government": IndustryPack(
        key="government", label="Government & public sector",
        tone="Formal. Arabic fluency and public-sector familiarity are assets.",
        certifications=["Project Management Professional (PMP)"],
        emphasis=["public-sector programmes", "Vision 2030 alignment",
                  "stakeholder management", "Arabic proficiency"],
    ),
    "other": IndustryPack(key="other", label="Other",
                          tone="Professional and clear.",
                          emphasis=["measurable outcomes", "scope of ownership"]),
}


def get_pack(key: str) -> IndustryPack:
    return PACKS.get((key or "other").lower(), PACKS["other"])


def prompt_fragment(key: str) -> str:
    pack = get_pack(key)
    lines = [f"Sector: {pack.label}.", f"Expected tone: {pack.tone}"]
    if pack.emphasis:
        lines.append("Screeners in this sector weigh: " + "; ".join(pack.emphasis) + ".")
    if pack.certifications:
        lines.append(
            "Credentials that carry weight here: " + "; ".join(pack.certifications)
            + ". Note them only if the resume already evidences them."
        )
    return "\n".join(lines)
