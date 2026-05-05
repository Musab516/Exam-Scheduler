import csv
from typing import List, Dict


def load_csv_results(filename="../comparison_results.csv") -> List[Dict]:
    # Load results from CSV file
    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            results = list(reader)
        print(f"Loaded {len(results)} results from {filename}")
        return results
    except FileNotFoundError:
        print(f"File not found: {filename}")
        return []


def generate_ascii_chart(title: str, labels: List[str], values: List[float], width=60):
    # Generate ASCII bar chart
    print(f"\n{title}")
    print("=" * (width + 20))

    if not values:
        print("No data to display")
        return

    max_val = max(values)
    min_val = min(values)

    for label, value in zip(labels, values):
        if max_val > min_val:
            bar_length = int((value - min_val) / (max_val - min_val) * width)
        else:
            bar_length = width // 2

        bar = "█" * bar_length + "░" * (width - bar_length)
        print(f"{label:<20} | {bar} | {value:.3f}")


def visualize_heuristics(results: List[Dict]):
    # Visualize heuristic comparison
    print("\n" + "=" * 80)
    print("HEURISTIC COMPARISON")
    print("=" * 80)

    heuristic_results = [r for r in results if 'SC(' in r.get('config_name', '')][:4]

    if len(heuristic_results) < 4:
        print("Not enough results for heuristic comparison")
        return

    configs = [r['config_name'].split('_')[0] for r in heuristic_results]
    times = [float(r['time_seconds']) for r in heuristic_results]
    nodes = [int(r['nodes_explored']) for r in heuristic_results]

    generate_ascii_chart("Execution Time (seconds)", configs, times, width=40)

    print("\nNode Exploration")
    print("=" * 70)

    max_nodes = max(nodes)

    for config, node_count in zip(configs, nodes):
        bar_length = int(node_count / max_nodes * 50) if max_nodes > 0 else 0
        bar = "▓" * bar_length + "░" * (50 - bar_length)
        print(f"{config:<20} | {bar} | {node_count}")


def visualize_soft_constraints(results: List[Dict]):
    # Visualize soft constraint trade-offs
    print("\n" + "=" * 80)
    print("SOFT CONSTRAINT ANALYSIS")
    print("=" * 80)

    soft_results = [r for r in results if 'SC(' in r.get('config_name', '')][-4:]

    if len(soft_results) < 4:
        print("Not enough results for soft constraint analysis")
        return

    labels = ["None", "Low", "Standard", "High"]
    times = [float(r['time_seconds']) for r in soft_results]
    qualities = [
        float(r['avg_solution_quality']) if r['avg_solution_quality'] else 0.0
        for r in soft_results
    ]
    violations = [int(r['soft_constraint_violations']) for r in soft_results]

    generate_ascii_chart("Time by Constraint Weight", labels, times, width=40)

    print("\nSolution Quality")
    print("=" * 70)

    max_quality = max(qualities) if qualities else 1

    for label, quality in zip(labels, qualities):
        bar_length = int(quality / max_quality * 50) if max_quality > 0 else 0
        bar = "█" * bar_length + "░" * (50 - bar_length)
        print(f"{label:<20} | {bar} | {quality:.2f}")

    print("\nSoft Constraint Violations")
    print("=" * 70)

    max_violations = max(violations) if violations else 1

    for label, v in zip(labels, violations):
        bar_length = int(v / max_violations * 50) if max_violations > 0 else 0
        bar = "█" * bar_length + "░" * (50 - bar_length)
        print(f"{label:<20} | {bar} | {v}")


def print_summary(results: List[Dict]):
    # Print summary statistics (CSP only)
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # Only CSP results (ignore random/greedy)
    csp_results = [r for r in results if 'SC(' in r.get('config_name', '')]

    successful = [r for r in csp_results if r['solution_found'] == 'True']
    failed = [r for r in csp_results if r['solution_found'] == 'False']

    print(f"\nTotal CSP configurations: {len(csp_results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")

    if not successful:
        print("\nNo successful CSP solutions for analysis")
        return

    times = [
        float(r['time_seconds'])
        for r in successful
        if r['time_seconds']
    ]

    nodes = [
        int(r['nodes_explored'])
        for r in successful
        if r['nodes_explored']
    ]

    qualities = [
        float(r['avg_solution_quality'])
        for r in successful
        if r['avg_solution_quality']
    ]

    if times:
        print("\nTiming")
        print(f"Min: {min(times):.3f}s")
        print(f"Max: {max(times):.3f}s")
        print(f"Avg: {sum(times)/len(times):.3f}s")

    if nodes:
        print("\nNodes")
        print(f"Min: {min(nodes)}")
        print(f"Max: {max(nodes)}")
        print(f"Avg: {sum(nodes)//len(nodes)}")

    print("\nQuality")
    if len(qualities) > 1:
        print(f"Min: {min(qualities):.2f}")
        print(f"Max: {max(qualities):.2f}")
        print(f"Avg: {sum(qualities)/len(qualities):.2f}")
    else:
        print("Not enough successful solutions for meaningful analysis")


def main():
    print("\nEXAM SCHEDULING CSP - VISUALIZATION\n")

    results = load_csv_results()

    if not results:
        print("No results found. Run experiments first.")
        return

    visualize_heuristics(results)
    visualize_soft_constraints(results)
    print_summary(results)
    print("\nObservation:")
    print("Only MRV + Degree + Forward Checking produced a valid solution.")


if __name__ == "__main__":
    main()