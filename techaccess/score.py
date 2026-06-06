"""TechAccess Scoring Engine.

Converts raw scan results into a 0-100 score with letter grade.
Weights issues by impact level and deduplicates across viewports.
"""

from dataclasses import dataclass

# Impact weights — how much each severity deducts from score
IMPACT_WEIGHTS = {
    "critical": 15,
    "serious": 10,
    "moderate": 5,
    "minor": 2,
}

GRADES = [
    (95, "A+"),
    (90, "A"),
    (85, "A-"),
    (80, "B+"),
    (75, "B"),
    (70, "B-"),
    (65, "C+"),
    (60, "C"),
    (55, "C-"),
    (50, "D+"),
    (45, "D"),
    (40, "D-"),
    (0, "F"),
]


@dataclass
class Score:
    """Accessibility score for a page."""
    value: int  # 0-100
    grade: str  # A+ through F
    total_issues: int
    critical: int
    serious: int
    moderate: int
    minor: int
    deductions: dict  # breakdown of point deductions

    def to_dict(self) -> dict:
        return {
            "score": self.value,
            "grade": self.grade,
            "total_issues": self.total_issues,
            "by_impact": {
                "critical": self.critical,
                "serious": self.serious,
                "moderate": self.moderate,
                "minor": self.minor,
            },
            "deductions": self.deductions,
        }


def calculate(issues: list) -> Score:
    """Calculate accessibility score from a list of Issues.

    Deduplicates by rule_id (same rule across viewports counts once).
    Score starts at 100 and deducts per unique rule violation.
    """
    # Deduplicate by rule_id for scoring (same issue on mobile+desktop = one deduction)
    seen_rules: dict[str, str] = {}  # rule_id -> highest impact
    impact_order = {"critical": 4, "serious": 3, "moderate": 2, "minor": 1}

    for issue in issues:
        rid = issue.rule_id
        impact = issue.impact
        if rid not in seen_rules or impact_order.get(impact, 0) > impact_order.get(seen_rules[rid], 0):
            seen_rules[rid] = impact

    # Calculate deductions
    deductions = {}
    total_deduction = 0
    for rule_id, impact in seen_rules.items():
        weight = IMPACT_WEIGHTS.get(impact, 2)
        deductions[rule_id] = {"impact": impact, "points": weight}
        total_deduction += weight

    value = max(0, 100 - total_deduction)

    # Determine grade
    grade = "F"
    for threshold, letter in GRADES:
        if value >= threshold:
            grade = letter
            break

    # Count by impact
    impacts = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    for issue in issues:
        impacts[issue.impact] = impacts.get(issue.impact, 0) + 1

    return Score(
        value=value,
        grade=grade,
        total_issues=len(issues),
        critical=impacts["critical"],
        serious=impacts["serious"],
        moderate=impacts["moderate"],
        minor=impacts["minor"],
        deductions=deductions,
    )
