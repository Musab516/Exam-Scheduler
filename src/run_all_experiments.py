import json
import csv
from solver.exam_scheduler_enhanced import solve_with_config, SolverConfig
from analysis.algorithm_comparison import random_assignment, greedy_assignment

def run_all():
    print("\n Running ALL configurations...\n")

    # Load dataset
    with open("dataset/data/medium.json") as f:
        data = json.load(f)

    results = []

    # CSP CONFIGURATIONS
    configs = [
        SolverConfig(False, False, False),  # Basic
        SolverConfig(True, False, False),   # MRV
        SolverConfig(True, True, False),    # MRV + Degree
        SolverConfig(True, True, True),     # Full (MRV + Degree + FC)
    ]

    print("------ CSP CONFIGS ------")

    for config in configs:
        print(f"\nRunning: {config.name()}")

        metrics = solve_with_config(data, config)
        results.append(metrics.to_dict())

        print(f"  Found: {metrics.solution_found}")
        print(f"  Time: {metrics.time_seconds}s")
        print(f"  Nodes: {metrics.nodes_explored}")

    # BASELINE ALGORITHMS
    print("\n------ BASELINES------")

    _, random_metrics = random_assignment(data)
    results.append(random_metrics.to_dict())

    print("Random done")

    _, greedy_metrics = greedy_assignment(data)
    results.append(greedy_metrics.to_dict())

    print("Greedy done")

    # SAVE RESULTS
    print("\n Saving results...")

    # collect all possible keys
    all_keys = set()
    for r in results:
        all_keys.update(r.keys())

    all_keys = list(all_keys)

    # normalize rows (fill missing values)
    normalized_results = []
    for r in results:
        row = {}
        for key in all_keys:
            row[key] = r.get(key, "")
        normalized_results.append(row)

    with open("comparison_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(normalized_results)

    print(" Results saved as comparison_results.csv")

    # QUICK SUMMARY
    print("\n SUMMARY\n")

    for r in results:
        name = r.get("config_name", r.get("algorithm_name"))
        print(f"{name}")
        print(f"  Found: {r['solution_found']}")
        print(f"  Time: {r['time_seconds']}s")
        print(f"  Nodes: {r.get('nodes_explored', 0)}")
        print("-" * 40)


if __name__ == "__main__":
    run_all()