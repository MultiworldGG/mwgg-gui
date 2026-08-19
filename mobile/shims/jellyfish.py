"""Mobile shim for the jellyfish library.

Utils.get_fuzzy_results lazily imports jellyfish for
damerau_levenshtein_distance — a live client path (fuzzy matching for
`!hint <item>` and command suggestions). jellyfish is a compiled (Rust)
package with no mobile wheels, and that one function is all the codebase
uses, so this provides a pure-Python optimal-string-alignment variant.
(OSA restricts transpositions vs. true Damerau-Levenshtein; for ranking
fuzzy matches the difference is irrelevant.)
"""


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if not len1:
        return len2
    if not len2:
        return len1

    prev2: list[int] = []
    prev = list(range(len2 + 1))
    for i in range(1, len1 + 1):
        current = [i] + [0] * len2
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            current[j] = min(
                prev[j] + 1,          # deletion
                current[j - 1] + 1,   # insertion
                prev[j - 1] + cost,   # substitution
            )
            if (i > 1 and j > 1
                    and s1[i - 1] == s2[j - 2]
                    and s1[i - 2] == s2[j - 1]):
                current[j] = min(current[j], prev2[j - 2] + 1)  # transposition
        prev2, prev = prev, current
    return prev[len2]
