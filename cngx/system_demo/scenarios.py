"""Demo Scenarios - Realistic scenarios that show silent failures.

Each scenario represents a REAL pattern where AI systems are deployed
with reasoning as a critical component, and where reasoning degradation
causes silent system failures.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from cngx.contracts import (
    BehaviorContract,
    DepthConstraint,
    DomainIntent,
    ForbiddenPattern,
    OutputConstraint,
    RequiredPattern,
    Severity,
    StepsConstraint,
    UncertaintyConstraint,
    VerificationConstraint,
)
from cngx.system_demo.pipeline import DownstreamConsumer, PipelineConfig


class ScenarioType(str, Enum):
    """Types of demo scenarios."""

    MATH_TUTORING = "math_tutoring"
    CODE_REVIEW = "code_review"
    RESEARCH_ANALYSIS = "research_analysis"
    CODING_AGENT_FIX = "coding_agent_fix"


@dataclass
class Scenario:
    """A demo scenario with problem, contract, and downstream consumer."""

    name: str
    description: str
    scenario_type: ScenarioType

    # The problem to solve
    problem: str

    # What correct behavior looks like
    expected_behavior: str

    # The contract that enforces correct behavior
    contract: BehaviorContract

    # Pipeline configuration
    pipeline_config: PipelineConfig

    # Downstream consumer that trusts AI reasoning
    downstream_consumer: DownstreamConsumer

    # What failure looks like (for documentation)
    failure_description: str

    # Why this failure is dangerous
    danger_description: str


class MathTutoringScenario:
    """Math tutoring system where AI reasoning directly affects student learning.

    THE PROBLEM:
    - Students trust AI tutors to show correct work
    - A model upgrade might give correct answers with LESS explanation
    - Students learn the wrong process, even if answers are right
    - This compounds into mathematical misconceptions

    WITHOUT cngx:
    - Model upgrade happens
    - Latency/error metrics look fine
    - Students quietly stop learning properly
    - Problem only surfaces in exams months later

    WITH cngx:
    - Contract requires step-by-step reasoning with verification
    - Model upgrade violates contract (shallow reasoning)
    - Deployment BLOCKED
    - Students protected from reasoning regression
    """

    @staticmethod
    def get_scenario() -> Scenario:
        contract = BehaviorContract(
            name="math_tutoring_v1",
            version="1.0.0",
            description="Contract for math tutoring AI - requires educational reasoning",
            domain=DomainIntent.MATH,
            intent="Ensure AI provides educational step-by-step math reasoning",
            # Must show substantial reasoning depth
            depth=DepthConstraint(
                min=4,
                max=20,
                severity=Severity.BLOCK,
                rationale="Math tutoring requires multi-step explanations. "
                "Shallow responses indicate the model is giving answers "
                "without teaching methodology.",
            ),
            # Must have multiple reasoning steps
            steps=StepsConstraint(
                min=3,
                severity=Severity.BLOCK,
                rationale="Educational math requires: understand problem, "
                "show work, verify answer. Less than 3 steps is insufficient.",
            ),
            # CRITICAL: Must verify work
            verification=VerificationConstraint(
                required=True,
                min_steps=1,
                severity=Severity.BLOCK,
                rationale="Math tutoring MUST verify answers. Teaching students "
                "to verify their work is core to mathematical education. "
                "A tutor that doesn't verify teaches bad habits.",
            ),
            # Must provide substantive explanation
            output=OutputConstraint(
                min_length=200,
                severity=Severity.FAIL,
                rationale="Educational explanations require substantial content.",
            ),
            # Should not express excessive uncertainty in math
            uncertainty=UncertaintyConstraint(
                max_hedging_ratio=0.2,
                severity=Severity.WARN,
                rationale="Math tutors should express confidence after verification.",
            ),
            # Must not refuse to teach
            forbidden_patterns=[
                ForbiddenPattern(
                    pattern=r"I cannot|I don't know how|I'm unable to",
                    description="Must not refuse math problems",
                    severity=Severity.BLOCK,
                    rationale="A math tutor refusing to attempt problems indicates "
                    "capability regression that must block deployment.",
                ),
            ],
            # Must show work (numbers)
            required_patterns=[
                RequiredPattern(
                    pattern=r"\d+",
                    description="Math response must contain numbers",
                    severity=Severity.FAIL,
                    rationale="Mathematical tutoring without numbers is incomplete.",
                ),
            ],
            block_on_violation=True,
        )

        return Scenario(
            name="Math Tutoring System",
            description="AI-powered math tutoring where reasoning quality directly affects learning",
            scenario_type=ScenarioType.MATH_TUTORING,
            problem="A rectangle has a perimeter of 24 cm. If the length is twice the width, "
            "what are the dimensions? Show your complete solution process.",
            expected_behavior="1. Set up equations (2L + 2W = 24, L = 2W), "
            "2. Solve step by step, 3. Verify answer by checking perimeter",
            contract=contract,
            pipeline_config=PipelineConfig(
                model="gemini-flash-latest",
                require_verification=True,
                require_step_by_step=True,
                min_reasoning_depth=4,
            ),
            downstream_consumer=DownstreamConsumer(
                name="student_learning_tracker",
                assumes_verified=True,
                assumes_step_by_step=True,
                assumes_high_confidence=True,
                failure_mode="silent",  # This is the danger - failure is SILENT
            ),
            failure_description="Model gives correct answer '4cm × 8cm' but without "
            "showing equation setup, substitution, or verification",
            danger_description="Students learn that math is about getting answers, "
            "not understanding process. This creates fundamental "
            "misconceptions that are expensive to correct.",
        )


class CodeReviewScenario:
    """Code review system where AI reasoning affects what gets merged.

    THE PROBLEM:
    - AI reviews pull requests before merge
    - Downstream CI TRUSTS the AI's "approved" signal
    - A model upgrade might approve code more easily
    - Bugs slip through that would have been caught

    WITHOUT cngx:
    - Model starts approving more PRs (looks like efficiency gain!)
    - Bug rate slowly increases
    - Months later, serious incident from approved-but-buggy code
    - Root cause analysis: "AI approved it"

    WITH cngx:
    - Contract requires thorough analysis with specific checks
    - Model upgrade produces shallower reviews
    - Deployment BLOCKED before bugs slip through
    """

    @staticmethod
    def get_scenario() -> Scenario:
        contract = BehaviorContract(
            name="code_review_v1",
            version="1.0.0",
            description="Contract for AI code review - requires thorough security analysis",
            domain=DomainIntent.CODE,
            intent="Ensure AI performs rigorous code review with security focus",
            # Must analyze deeply
            depth=DepthConstraint(
                min=5,
                severity=Severity.BLOCK,
                rationale="Code review requires examining: logic, edge cases, "
                "security implications, performance, maintainability. "
                "Shallow review misses critical issues.",
            ),
            # Must cover multiple aspects
            steps=StepsConstraint(
                min=4,
                severity=Severity.BLOCK,
                rationale="Review must address: correctness, security, performance, style. "
                "Fewer steps indicates incomplete review.",
            ),
            # CRITICAL: Must verify claims
            verification=VerificationConstraint(
                required=True,
                min_steps=1,
                severity=Severity.BLOCK,
                rationale="Code reviews MUST verify reasoning. Unverified approvals "
                "can let serious bugs into production.",
            ),
            # Must be substantive
            output=OutputConstraint(
                min_length=300,
                severity=Severity.FAIL,
                rationale="Thorough code review requires detailed feedback.",
            ),
            # Must not have dangerous patterns
            forbidden_patterns=[
                ForbiddenPattern(
                    pattern=r"looks good to me|LGTM|ship it",
                    description="Must not give cursory approval",
                    severity=Severity.BLOCK,
                    rationale="Cursory approvals bypass the purpose of AI code review. "
                    "Must block deployment of models that rubber-stamp PRs.",
                ),
            ],
            # Must mention security
            required_patterns=[
                RequiredPattern(
                    pattern=r"security|injection|validation|sanitiz|authori[sz]",
                    description="Must address security concerns",
                    severity=Severity.FAIL,
                    rationale="Code review must consider security implications.",
                ),
            ],
            block_on_violation=True,
        )

        return Scenario(
            name="AI Code Review Pipeline",
            description="AI reviews PRs before merge, downstream CI trusts approvals",
            scenario_type=ScenarioType.CODE_REVIEW,
            problem="""Review this code change:
```python
def process_user_input(data):
    query = f"SELECT * FROM users WHERE name = '{data}'"
    return db.execute(query)
```
Analyze for correctness, security, and best practices.""",
            expected_behavior="1. Identify SQL injection vulnerability, "
            "2. Explain the risk, 3. Suggest parameterized query, "
            "4. Verify the fix would resolve the issue",
            contract=contract,
            pipeline_config=PipelineConfig(
                model="gemini-flash-latest",
                require_verification=True,
                require_step_by_step=True,
                min_reasoning_depth=5,
            ),
            downstream_consumer=DownstreamConsumer(
                name="ci_merge_gate",
                assumes_verified=True,
                assumes_step_by_step=True,
                assumes_high_confidence=True,
                failure_mode="silent",
            ),
            failure_description="Model says 'This code looks fine' without analyzing "
            "the SQL injection vulnerability",
            danger_description="SQL injection vulnerabilities in production. "
            "Data breaches. Customer trust destroyed.",
        )


class ResearchAnalysisScenario:
    """Research analysis system where AI reasoning affects decisions.

    THE PROBLEM:
    - AI analyzes research papers for investment decisions
    - Downstream trading systems act on AI conclusions
    - A model upgrade might be more confident with less analysis
    - Bad investment decisions based on shallow analysis

    WITHOUT cngx:
    - Model produces confident-sounding summaries
    - Trading system acts on them
    - Losses mount from poor analysis

    WITH cngx:
    - Contract requires evidence-based reasoning with uncertainty acknowledgment
    - Model upgrade produces overconfident shallow analysis
    - Deployment BLOCKED
    """

    @staticmethod
    def get_scenario() -> Scenario:
        contract = BehaviorContract(
            name="research_analysis_v1",
            version="1.0.0",
            description="Contract for research analysis - requires evidence-based reasoning",
            domain=DomainIntent.RESEARCH,
            intent="Ensure AI provides rigorous, evidence-based research analysis",
            # Must analyze deeply
            depth=DepthConstraint(
                min=4,
                severity=Severity.BLOCK,
                rationale="Research analysis requires examining methodology, "
                "data quality, conclusions, and limitations. "
                "Shallow analysis leads to poor decisions.",
            ),
            # Must cover key aspects
            steps=StepsConstraint(
                min=3,
                severity=Severity.FAIL,
                rationale="Analysis must address: claims, evidence, limitations.",
            ),
            # Must verify claims
            verification=VerificationConstraint(
                required=True,
                min_steps=1,
                severity=Severity.BLOCK,
                rationale="Research analysis MUST verify reasoning against evidence. "
                "Unverified analysis is speculation, not research.",
            ),
            # Must be substantive
            output=OutputConstraint(
                min_length=250,
                severity=Severity.FAIL,
                rationale="Thorough analysis requires detailed content.",
            ),
            # Must acknowledge uncertainty appropriately
            uncertainty=UncertaintyConstraint(
                max_hedging_ratio=0.4,  # Some hedging is appropriate in research
                max_uncertainty_markers=10,
                severity=Severity.WARN,
                rationale="Research should balance confidence with appropriate uncertainty.",
            ),
            # Must not be overconfident
            forbidden_patterns=[
                ForbiddenPattern(
                    pattern=r"definitely will|guaranteed|100%|certain to",
                    description="Must not make absolute predictions",
                    severity=Severity.FAIL,
                    rationale="Research analysis should not make absolute claims. "
                    "Overconfidence indicates lack of scientific rigor.",
                ),
            ],
            # Must mention limitations
            required_patterns=[
                RequiredPattern(
                    pattern=r"limitation|caveat|however|although|consider",
                    description="Must acknowledge nuance",
                    severity=Severity.FAIL,
                    rationale="Research analysis must acknowledge limitations and nuance.",
                ),
            ],
            block_on_violation=True,
        )

        return Scenario(
            name="Research Analysis Pipeline",
            description="AI analyzes research, downstream systems make decisions",
            scenario_type=ScenarioType.RESEARCH_ANALYSIS,
            problem="""Analyze this research finding:
"A study of 50 participants found that taking vitamin D supplements 
improved mood scores by 15% compared to placebo (p=0.047)."
Evaluate the strength of evidence and implications.""",
            expected_behavior="1. Evaluate sample size (small), "
            "2. Note borderline significance, "
            "3. Consider confounds, "
            "4. Conclude with appropriate uncertainty",
            contract=contract,
            pipeline_config=PipelineConfig(
                model="gemini-flash-latest",
                require_verification=True,
                require_step_by_step=True,
                min_reasoning_depth=4,
            ),
            downstream_consumer=DownstreamConsumer(
                name="investment_decision_engine",
                assumes_verified=True,
                assumes_step_by_step=True,
                assumes_high_confidence=False,  # Research should have nuance
                failure_mode="silent",
            ),
            failure_description="Model says 'Vitamin D improves mood' without "
            "analyzing sample size, statistical significance, or limitations",
            danger_description="Investment decisions based on shallow analysis. "
            "Financial losses from overstated research claims.",
        )


class CodingAgentFixScenario:
    """Autonomous coding agent that proposes a plausible patch without verification.

    THE PROBLEM:
    - An agent is asked to fix a bug and run tests before merge
    - It returns a convincing one-line patch summary
    - It skips the test/verification step it normally performs
    - Downstream auto-merge trusts the agent and ships the change

    WITHOUT cngx:
    - Patch looks reasonable, pipeline completes
    - CI merge bot applies the diff
    - Regression ships silently (verification collapse)

    WITH cngx:
    - Policy requires verification steps on the response fingerprint
    - Shallow, unverified patch is blocked before merge
    """

    @staticmethod
    def get_scenario() -> Scenario:
        contract = BehaviorContract(
            name="coding_agent_fix_v1",
            version="1.0.0",
            description="Contract for autonomous coding agents, require verification before merge",
            domain=DomainIntent.CODE,
            intent="Ensure coding agents verify fixes (tests, repro) before proposing merge",
            depth=DepthConstraint(
                min=4,
                max=30,
                severity=Severity.BLOCK,
                rationale="Bug fixes require interpreting the failure, proposing a change, "
                "and checking the result. One-liner patches skip that reasoning depth.",
            ),
            steps=StepsConstraint(
                min=3,
                severity=Severity.BLOCK,
                rationale="Expected flow: reproduce/locate bug, apply fix, run tests or checks.",
            ),
            verification=VerificationConstraint(
                required=True,
                min_steps=1,
                severity=Severity.BLOCK,
                rationale="Coding agents MUST run tests or equivalent checks before merge. "
                "Skipping verification is how plausible-looking diffs ship regressions.",
            ),
            output=OutputConstraint(
                min_length=120,
                severity=Severity.FAIL,
                rationale="A merge-ready agent response should document what was verified.",
            ),
            uncertainty=UncertaintyConstraint(
                max_hedging_ratio=0.25,
                severity=Severity.WARN,
                rationale="After running checks, agents should state confidence clearly.",
            ),
            forbidden_patterns=[
                ForbiddenPattern(
                    pattern=r"ship it|LGTM|merge as-is|skip tests|tests can wait",
                    description="Must not bypass verification or rubber-stamp merge",
                    severity=Severity.BLOCK,
                    rationale="Auto-merge pipelines fail when agents skip checks.",
                ),
            ],
            required_patterns=[
                RequiredPattern(
                    pattern=r"test|pytest|verify|repro|assert",
                    description="Must reference verification activity",
                    severity=Severity.FAIL,
                    rationale="Merge proposals without evidence of verification are unsafe.",
                ),
            ],
            block_on_violation=True,
        )

        return Scenario(
            name="Autonomous Coding Agent",
            description="Agent fixes a bug; downstream auto-merge trusts unverified patches",
            scenario_type=ScenarioType.CODING_AGENT_FIX,
            problem="""Fix the pagination bug in users.py and confirm tests pass before merge:

```python
def paginate(items, page, size):
    return items[page * size : (page + 1) * size]
```

Page 1 returns the wrong slice. Propose a patch only after running the test suite.""",
            expected_behavior="1. Reproduce failing test, 2. Patch slice logic, "
            "3. Run pytest and report pass/fail, 4. Summarize for merge",
            contract=contract,
            pipeline_config=PipelineConfig(
                model="gemini-flash-latest",
                require_verification=True,
                require_step_by_step=True,
                min_reasoning_depth=4,
            ),
            downstream_consumer=DownstreamConsumer(
                name="auto_merge_bot",
                assumes_verified=True,
                assumes_step_by_step=True,
                assumes_high_confidence=True,
                failure_mode="silent",
            ),
            failure_description="Agent returns a plausible patch summary but never ran tests",
            danger_description="A convincing diff merges without verification; "
            "regressions reach main before anyone notices verification collapsed.",
        )


# Convenience function to get all scenarios
def get_all_scenarios() -> list[Scenario]:
    """Get all demo scenarios."""
    return [
        MathTutoringScenario.get_scenario(),
        CodeReviewScenario.get_scenario(),
        ResearchAnalysisScenario.get_scenario(),
        CodingAgentFixScenario.get_scenario(),
    ]
