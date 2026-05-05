import json
import csv
from typing import List, Dict
import statistics

# =========================
# RESULTS ANALYSIS & VISUALIZATION
# =========================

class ResultsAnalyzer:
    # Analyze and visualize comparison results
    
    def __init__(self, csv_file="../comparison_results.csv", json_file="../../comparison_results.json"):
        self.csv_file = csv_file
        self.json_file = json_file
        self.results = []
        self.load_results()
    
    def load_results(self):
        # Load results from CSV
        try:
            with open(self.csv_file, 'r') as f:
                reader = csv.DictReader(f)
                self.results = list(reader)
            print(f"Loaded {len(self.results)} results from {self.csv_file}")
        except FileNotFoundError:
            print(f"Results file not found: {self.csv_file}")
    
    def create_comparison_table(self):
        # Create formatted comparison table
        print("\n" + "=" * 100)
        print("DETAILED COMPARISON TABLE")
        print("=" * 100 + "\n")
        
        print(f"{'Configuration':<35} {'Found':<8} {'Time (s)':<12} {'Nodes':<12} {'Quality':<12} {'Soft Viol.':<12}")
        print("-" * 100)
        
        for result in self.results:
            if not result.get('config_name'):
                continue
            config = result['config_name']
            found = "Yes" if result['solution_found'] == "True" else "No"
            time_s = f"{float(result['time_seconds']):.3f}"
            nodes = result['nodes_explored']
            quality = f"{float(result['avg_solution_quality']):.2f}" if result['avg_solution_quality'] else "N/A"
            violations = result['soft_constraint_violations']
            
            print(f"{config:<35} {found:<8} {time_s:<12} {nodes:<12} {quality:<12} {violations:<12}")
    
    def create_speedup_analysis(self):
        # Analyze speedup of heuristic configurations
        print("\n" + "=" * 70)
        print("SPEEDUP ANALYSIS (Relative to Baseline)")
        print("=" * 70 + "\n")
        
        heuristic_configs = [r for r in self.results if 'SC(' in r['config_name']][:4]
        
        if not heuristic_configs:
            print("No heuristic comparison results found")
            return
        
        baseline_time = float(heuristic_configs[0]['time_seconds'])
        baseline_nodes = int(heuristic_configs[0]['nodes_explored'])
        
        print(f"Baseline (Basic): {baseline_time:.3f}s | {baseline_nodes} nodes\n")
        
        for result in heuristic_configs[1:]:
            config = result['config_name']
            time_s = float(result['time_seconds'])
            nodes = int(result['nodes_explored'])
            
            time_speedup = baseline_time / time_s if time_s > 0 else float('inf')
            node_reduction = (1 - nodes / baseline_nodes) * 100 if baseline_nodes > 0 else 0
            
            print(f"{config:<35}")
            print(f"  Time Speedup: {time_speedup:.2f}x ({time_s:.3f}s)")
            print(f"  Node Reduction: {node_reduction:+.1f}% ({nodes} nodes)")
    
    def create_quality_analysis(self):
        print("\n" + "=" * 70)
        print("SOLUTION QUALITY ANALYSIS")
        print("=" * 70 + "\n")
        
        successful = [
            r for r in self.results
            if r['solution_found'] == 'True' and 'SC(' in r.get('config_name', '')
        ]
        
        if not successful:
            print("No successful CSP solutions found")
            return
        
        print(f"Successful CSP Solutions: {len(successful)}\n")
        
        print(f"{'Configuration':<35} {'Quality':<12} {'Soft Violations':<15}")
        print("-" * 70)
        
        for result in successful:
            config = result['config_name']
            quality = float(result['avg_solution_quality']) if result['avg_solution_quality'] else 0.0
            violations = int(result['soft_constraint_violations']) if result['soft_constraint_violations'] else 0
            
            print(f"{config:<35} {quality:<12.2f} {violations:<15}")
    
    def create_trade_off_analysis(self):
        # Analyze time vs quality trade-offs
        print("\n" + "=" * 70)
        print("TIME vs QUALITY TRADE-OFF")
        print("=" * 70 + "\n")
        
        soft_configs = [r for r in self.results if 'SC(' in r['config_name']][-4:]
        
        if len(soft_configs) < 4:
            print("Not enough soft constraint results")
            return
        
        print(f"{'Constraint Weight':<25} {'Time (s)':<12} {'Quality':<12} {'Soft Viol.':<12}")
        print("-" * 70)
        
        labels = ["No Constraints", "Low", "Standard", "High"]
        
        for result, label in zip(soft_configs, labels):
            time_s = float(result['time_seconds'])
            quality = float(result['avg_solution_quality']) if result['avg_solution_quality'] else 0.0
            violations = int(result['soft_constraint_violations'])
            
            print(f"{label:<25} {time_s:<12.3f} {quality:<12.2f} {violations:<12}")
    
    def create_key_findings(self):
        # Generate key findings
        print("\n" + "=" * 70)
        print("KEY FINDINGS")
        print("=" * 70 + "\n")
        
        successful = [
            r for r in self.results
            if r['solution_found'] == 'True' and 'SC(' in r.get('config_name', '')
        ]
        failed = [r for r in self.results if r['solution_found'] == 'False']
        
        print("Solver Success Rate")
        print(f"  Total: {len(successful)}/{len(self.results)}")
        
        if failed:
            print("  Failed configurations:")
            for r in failed:
                print(f"   - {r['config_name']}")
        print()
        
        heuristic_configs = [r for r in self.results if 'SC(' in r['config_name']][:4]
        
        print("Forward Checking Impact")
        if len(heuristic_configs) >= 4:
            fc_time = float(heuristic_configs[3]['time_seconds'])
            no_fc_time = float(heuristic_configs[2]['time_seconds'])
            improvement = (no_fc_time - fc_time) / no_fc_time * 100
            print(f"  Improvement: {improvement:.1f}% faster")
        print()
        
        print("Recommendation")
        if successful:
            best = min(successful, key=lambda r: float(r['time_seconds']))
            print(f"  Best configuration: {best['config_name']}")
    
    def create_markdown_report(self, filename="../../ANALYSIS_REPORT.md"):
        # Generate markdown report
        print(f"\nGenerating Markdown report: {filename}")
        
        with open(filename, 'w') as f:
            f.write("# Exam Scheduling CSP - Analysis Report\n\n")
            
            successful = len([r for r in self.results if r['solution_found'] == 'True'])
            f.write(f"- Configurations: {len(self.results)}\n")
            f.write(f"- Successful: {successful}\n\n")
            
            f.write("| Config | Found | Time | Nodes | Quality |\n")
            f.write("|---|---|---|---|---|\n")
            
            for r in self.results:
                found = "Yes" if r['solution_found'] == 'True' else "No"
                time_s = f"{float(r['time_seconds']):.3f}"
                quality = r['avg_solution_quality'] if r['avg_solution_quality'] else "N/A"
                
                f.write(f"| {r['config_name']} | {found} | {time_s} | {r['nodes_explored']} | {quality} |\n")
        
        print(f"Report saved to {filename}")


def main():
    analyzer = ResultsAnalyzer()
    
    if analyzer.results:
        analyzer.create_comparison_table()
        analyzer.create_speedup_analysis()
        analyzer.create_quality_analysis()
        analyzer.create_trade_off_analysis()
        analyzer.create_key_findings()
        analyzer.create_markdown_report()
    else:
        print("No results to analyze. Run experiments first.")


if __name__ == "__main__":
    main()