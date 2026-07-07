"""
Sample LLM outputs that represent real-world reasoning patterns.
These are handcrafted to exercise every fingerprinting metric, contract constraint,
and edge case in the Cogscope pipeline.
"""

# ============================================================================
# GOOD REASONING — Deep, verified, structured
# ============================================================================

GOOD_MATH_REASONING = """
Step 1: Understanding the problem
We need to solve the quadratic equation x² + 5x + 6 = 0.

Step 2: Factoring the quadratic
I need to find two numbers that multiply to 6 and add to 5.
The factors of 6 are: (1,6), (2,3), (-1,-6), (-2,-3).
The pair (2,3) sums to 5. Therefore x² + 5x + 6 = (x + 2)(x + 3).

Step 3: Solving for x
Setting each factor to zero:
x + 2 = 0  →  x = -2
x + 3 = 0  →  x = -3

Step 4: Verification
Let me verify by substituting back:
For x = -2: (-2)² + 5(-2) + 6 = 4 - 10 + 6 = 0 ✓
For x = -3: (-3)² + 5(-3) + 6 = 9 - 15 + 6 = 0 ✓

Therefore, the solutions are x = -2 and x = -3.

The answer is x = -2 and x = -3.
"""

GOOD_CODE_REVIEW = """
Step 1: Reading the code structure
The function `process_data` takes a list of dictionaries and transforms them. Let me trace through the logic.

Step 2: Analyzing the algorithm
The nested loop has O(n²) complexity. For each item, it searches for matches in the entire list.
I can see that the `key` parameter is used for grouping, and `value` is the aggregation target.

Step 3: Identifying issues
1. The variable `temp` is reused across iterations — this could cause data leakage between groups
2. The `try/except` on line 15 catches `Exception` broadly — this hides specific errors
3. No input validation — if `data` is None, this crashes with AttributeError

Step 4: Checking edge cases
- Empty list: Returns empty dict (correct)
- Single item: Works correctly
- Duplicate keys: Last value wins (is this intended?)
- None values in list: Crashes at line 8

Step 5: Verification
Let me double-check my analysis of the O(n²) claim:
The outer loop runs n times, inner loop runs n times for each. Yes, O(n²) is confirmed.
For n=10000, that's 100M operations — definitely a performance concern.

The code is functional but has 3 bugs and a performance issue that should be addressed before production use.
"""

GOOD_RESEARCH = """
Step 1: Examining the claim
The question asks whether increasing minimum wage reduces employment. This is a heavily studied topic in labor economics.

Step 2: Reviewing the evidence
The landmark study by Card and Krueger (1994) examined fast food employment in New Jersey vs Pennsylvania after a minimum wage increase. They found no significant negative employment effect.

However, Neumark and Wascher (2007) meta-analyzed 102 studies and found that about two-thirds reported negative employment effects, particularly for low-skilled workers.

Step 3: Considering methodological differences
The disagreement stems from methodology:
- Natural experiment studies (Card-Krueger style) tend to find small or no effects
- Time-series regression studies tend to find negative effects
- The "bunching" estimator approach (Cengiz et al., 2019) found job loss concentrated just below the new minimum, but overall employment effects were small

Step 4: Synthesizing
The current empirical consensus, as summarized by Dube (2019), is that moderate minimum wage increases (up to ~60% of median wage) have minimal disemployment effects. Large increases in low-wage areas show clearer negative effects.

Step 5: Verification
Let me verify this synthesis is consistent: Card-Krueger studied a moderate increase, Neumark-Wascher included studies of varying magnitudes. The "moderate vs large" framework reconciles both.

The evidence suggests moderate minimum wage increases do not significantly reduce employment, but large increases may, particularly affecting young and low-skilled workers.
"""

# ============================================================================
# BAD REASONING — Shallow, no verification, overconfident
# ============================================================================

SHALLOW_MATH = "The answer is x = -2 and x = -3."

SHALLOW_CODE_REVIEW = "The code looks fine. No issues found."

SHALLOW_RESEARCH = (
    "Yes, increasing minimum wage reduces employment because basic economics says so."
)

# ============================================================================
# HEDGING / UNCERTAIN REASONING
# ============================================================================

HEDGING_RESPONSE = """
Well, I think maybe the answer might be around 42, but I'm not really sure.
It could possibly be different. Perhaps if we look at it from another angle,
the answer might change. I'm uncertain about this, but it seems like it could
be correct. Maybe. Possibly the calculation is right, but I'm not confident.
"""

OVERCONFIDENT_WRONG = """
The answer is definitely 7. This is clearly the only possible answer.
Without doubt, 7 is correct. I'm absolutely certain about this.
Obviously, anyone can see that 7 is the right answer. No question about it.
"""

# ============================================================================
# SELF-CORRECTING REASONING
# ============================================================================

SELF_CORRECTING = """
Step 1: Let me try factoring x² + 5x + 7.
I need numbers that multiply to 7 and add to 5. That would be... 1 and 7? No, wait, 1 + 7 = 8 ≠ 5.

Actually, let me reconsider. My mistake — this quadratic doesn't factor neatly over integers.

Step 2: Using the quadratic formula
x = (-b ± √(b² - 4ac)) / 2a
x = (-5 ± √(25 - 28)) / 2
x = (-5 ± √(-3)) / 2

Step 3: Scratch that — let me double-check. The discriminant is 25 - 28 = -3, which is negative.
This means there are no real solutions, only complex ones.

Step 4: The solutions are x = (-5 ± i√3) / 2

Let me verify: if x = (-5 + i√3)/2, then x² = (25 - 2·5·i√3 - 3)/4 = (22 - 10i√3)/4
5x = (-25 + 5i√3)/2 = (-50 + 10i√3)/4
x² + 5x + 7 = (22 - 10i√3 - 50 + 10i√3 + 28)/4 = 0/4 = 0 ✓

The answer is x = (-5 ± i√3) / 2.
"""

# ============================================================================
# TOOL-HEAVY REASONING
# ============================================================================

TOOL_HEAVY_RESPONSE = """
Step 1: I'll use the calculator to solve this.

[Using calculator: 2 + 2 = 4]

Step 2: Now let me search for the formula.

[Using web_search: "quadratic formula"]

Step 3: Let me verify with another tool.

[Using code_executor: solving x^2 + 5x + 6 = 0]

Result: The solutions are x = -2 and x = -3.
"""

# ============================================================================
# LONG-FORM VERBOSE RESPONSE
# ============================================================================

VERBOSE_RESPONSE = """
First, I want to make sure I understand the problem correctly. The question is asking us to solve a mathematical equation. Specifically, it's a quadratic equation of the form ax² + bx + c = 0 where a = 1, b = 5, and c = 6.

Now, before I dive into solving this, let me explain what a quadratic equation is. A quadratic equation is a second-degree polynomial equation in a single variable. The general form is ax² + bx + c = 0 where a ≠ 0. These equations are fundamental in algebra and appear in many real-world applications.

There are several methods to solve a quadratic equation:
1. Factoring
2. Completing the square
3. Using the quadratic formula
4. Graphing

For this particular problem, I'll use the factoring method because the coefficients are small integers similar to what we might see in a textbook example.

Second, let me identify the factors. We need two numbers that multiply to give us c = 6 and add to give us b = 5. Let me systematically list all factor pairs of 6:
- 1 × 6 = 6, and 1 + 6 = 7 (not 5)
- 2 × 3 = 6, and 2 + 3 = 5 (yes!)
- (-1) × (-6) = 6, and (-1) + (-6) = -7 (not 5)
- (-2) × (-3) = 6, and (-2) + (-3) = -5 (not 5)

Third, now that I've found the right factor pair (2, 3), I can write the factored form:
x² + 5x + 6 = (x + 2)(x + 3) = 0

Fourth, setting each factor equal to zero:
- x + 2 = 0, which gives x = -2
- x + 3 = 0, which gives x = -3

Finally, let me verify both solutions to make sure they're correct:
For x = -2: (-2)² + 5(-2) + 6 = 4 - 10 + 6 = 0 ✓
For x = -3: (-3)² + 5(-3) + 6 = 9 - 15 + 6 = 0 ✓

Therefore, the solutions are x = -2 and x = -3.
"""

# ============================================================================
# MINIMAL / TERSE RESPONSE
# ============================================================================

TERSE_RESPONSE = "x = -2, -3"

# ============================================================================
# STRUCTURED CODE OUTPUT
# ============================================================================

STRUCTURED_CODE = """
Here is the solution:

```python
import numpy as np

def solve_quadratic(a, b, c):
    discriminant = b**2 - 4*a*c
    if discriminant < 0:
        return None  # No real solutions
    x1 = (-b + np.sqrt(discriminant)) / (2*a)
    x2 = (-b - np.sqrt(discriminant)) / (2*a)
    return x1, x2

# Solve x² + 5x + 6 = 0
result = solve_quadratic(1, 5, 6)
print(f"Solutions: x = {result[0]}, x = {result[1]}")
```

Output:
```
Solutions: x = -2.0, x = -3.0
```

The solutions are x = -2 and x = -3.
"""

# ============================================================================
# REFUSAL RESPONSE
# ============================================================================

REFUSAL_RESPONSE = "I cannot help with that request. I'm unable to provide that information."

# ============================================================================
# MULTILINGUAL RESPONSE
# ============================================================================

MULTILINGUAL_RESPONSE = """
La solución de la ecuación x² + 5x + 6 = 0 es:

Step 1: Factorizamos: (x + 2)(x + 3) = 0
Step 2: Las soluciones son x = -2 y x = -3
Step 3: Verificación: (-2)² + 5(-2) + 6 = 0 ✓

The answer is x = -2 and x = -3.
"""

# ============================================================================
# EMPTY & EDGE CASES
# ============================================================================

EMPTY_RESPONSE = ""
WHITESPACE_ONLY = "   \n\n\t  "
SINGLE_WORD = "42"
VERY_LONG = "This is a test. " * 5000  # ~80K chars
UNICODE_HEAVY = "The answer is π ≈ 3.14159... and √2 ≈ 1.41421... with ∑ = ∫ × ÷ ± ≤ ≥ ≠"
