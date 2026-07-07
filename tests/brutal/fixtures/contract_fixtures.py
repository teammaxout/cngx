"""
Contract fixtures for testing — covers every constraint type and severity level.
"""

STRICT_MATH_CONTRACT = """
name: strict_math_solver
version: "1.0"
domain: math
description: "Strict contract for math reasoning — blocks shallow answers"

depth:
  min: 3
  severity: block
  rationale: "Math must show multi-step reasoning"

steps:
  min: 2
  severity: fail
  rationale: "Must show work in at least 2 steps"

verification:
  required: true
  min_steps: 1
  severity: block
  rationale: "Math answers must be verified"

output:
  min_length: 50
  severity: warn

uncertainty:
  max_hedging_ratio: 0.3
  severity: fail
  rationale: "Math solver should be confident"

forbidden_patterns:
  - pattern: "I cannot|I'm unable|I don't know"
    severity: block
    rationale: "Must not refuse math questions"
"""

LENIENT_CONTRACT = """
name: lenient_check
version: "1.0"
domain: general
description: "Very lenient — almost everything passes"

depth:
  min: 1
  severity: warn

output:
  min_length: 1
  severity: warn
"""

IMPOSSIBLE_CONTRACT = """
name: impossible_contract
version: "1.0"
domain: general
description: "Impossibly strict — nothing can pass"

depth:
  min: 100
  max: 100
  severity: block

steps:
  min: 50
  severity: block

verification:
  required: true
  min_steps: 20
  severity: block

output:
  min_length: 100000
  max_length: 100001
  severity: block

uncertainty:
  max_hedging_ratio: 0.0
  severity: block
"""

CODE_REVIEW_CONTRACT = """
name: code_reviewer
version: "2.0"
domain: code
description: "Contract for code review tasks"

depth:
  min: 3
  severity: block
  rationale: "Code reviews must be thorough"

verification:
  required: true
  min_steps: 1
  severity: fail
  rationale: "Must verify findings"

output:
  min_length: 100
  severity: warn

required_patterns:
  - pattern: "bug|issue|error|concern|problem|vulnerability"
    severity: fail
    rationale: "Code review must identify at least one concern"

forbidden_patterns:
  - pattern: "looks good|LGTM|no issues"
    severity: block
    rationale: "Trivial approvals are not allowed"
"""

RESEARCH_CONTRACT = """
name: research_analyst
version: "1.0"
domain: research
description: "Contract for research and analysis tasks"

depth:
  min: 4
  severity: block
  rationale: "Research requires deep analysis"

steps:
  min: 3
  severity: fail

verification:
  required: true
  min_steps: 1
  severity: fail

uncertainty:
  max_hedging_ratio: 0.5
  severity: warn
  rationale: "Some hedging is acceptable in research"

output:
  min_length: 200
  severity: fail
"""

ALL_CONSTRAINTS_CONTRACT = """
name: all_constraints_test
version: "1.0"
domain: general
description: "Tests every constraint type"

depth:
  min: 2
  max: 20
  severity: block

steps:
  min: 2
  max: 30
  severity: fail

verification:
  required: true
  min_steps: 1
  severity: block

tools:
  max_calls: 10
  severity: warn

uncertainty:
  max_hedging_ratio: 0.4
  severity: fail

output:
  min_length: 100
  max_length: 50000
  severity: warn

forbidden_patterns:
  - pattern: "I cannot|I'm unable"
    severity: block
  - pattern: "as an AI"
    severity: warn

required_patterns:
  - pattern: "therefore|thus|hence|in conclusion|the answer"
    severity: fail
"""

WARN_ONLY_CONTRACT = """
name: warn_only
version: "1.0"
domain: general
description: "Only warns, never blocks"

depth:
  min: 5
  severity: warn

output:
  min_length: 500
  severity: warn

uncertainty:
  max_hedging_ratio: 0.1
  severity: warn
"""
