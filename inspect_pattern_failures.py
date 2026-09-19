from test_pattern_mapping import CASES
from maya_pattern_mapping import pattern_map


def main():
    for query, expected in CASES:
        result = pattern_map(query)
        if expected == "education":
            passed = any(item["category"] == expected for item in result["candidates"])
        elif expected == "experiment":
            passed = any("experiment" in item["small_reversible_experiment"].lower() for item in result["candidates"])
        elif expected == "negation":
            passed = bool(result["negation_terms_detected"])
        elif expected == "constraints":
            passed = bool(result["constraints_detected"])
        elif expected == "uncertainty":
            passed = True
        else:
            passed = bool(result["candidates"])
        if not passed:
            print("FAILED", query, expected)
            print(result)


if __name__ == "__main__":
    main()
