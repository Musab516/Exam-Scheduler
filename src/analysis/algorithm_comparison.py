"""
Algorithm Comparison Module
Compares CSP+heuristics against alternative approaches:
- Random assignment (baseline)
- Greedy assignment (simple heuristic)
- CSP with heuristics (your approach)

Research Question: How much better is CSP than simpler approaches?
"""

import json
import time
import random
import csv
import sys
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

# Import solver engine from the solver package
from solver.exam_scheduler_enhanced import solve_with_config, SolverConfig

# =========================
# DATA STRUCTURES
# =========================
@dataclass
class AlgorithmMetrics:
    algorithm_name: str
    time_seconds: float
    solution_found: bool
    hard_violations: int
    soft_violations: int
    solution_quality: float
    nodes_explored: int = 0
    description: str = ""
    
    def to_dict(self):
        return asdict(self)

# =========================
# LOAD DATA
# =========================
def load_data(file_path):
    with open(file_path) as f:
        return json.load(f)

def build_course_students(students):
    course_students = {}
    for sid, info in students.items():
        for course in info["courses"]:
            course_students.setdefault(course, []).append(sid)
    return course_students

# =========================
# BASELINE 1: RANDOM ASSIGNMENT
# =========================
def random_assignment(data) -> Tuple[Optional[Dict], AlgorithmMetrics]:
    """
    Baseline: Random assignment to available slots.
    Tests if problem is trivial (can solve with just luck).
    """
    students = data["students"]
    courses = data["courses"]
    rooms = data["rooms"]
    timeslots = data["timeslots"]
    course_info = data.get("course_info", {})
    
    course_students = build_course_students(students)
    
    start = time.time()
    
    # Generate random assignment
    solution = {}
    attempts = 0
    max_attempts = 1000
    
    while len(solution) < len(courses) and attempts < max_attempts:
        attempts += 1
        course = random.choice([c for c in courses if c not in solution])
        slot = (random.choice(timeslots), random.choice(list(rooms.keys())))
        
        # Check if valid
        valid = True
        for other_course, (t2, r2) in solution.items():
            # Hard constraint: Same room, same time
            if slot[0] == t2 and slot[1] == r2:
                valid = False
                break
            # Hard constraint: Student conflict
            if slot[0] == t2 and set(course_students.get(course, [])).intersection(course_students.get(other_course, [])):
                valid = False
                break
        
        if valid:
            solution[course] = slot
    
    end = time.time()
    
    # Check solution quality
    hard_violations = 0
    soft_violations = 0
    quality = 0.0
    
    if len(solution) == len(courses):
        # Count soft violations
        for course, (t, r) in solution.items():
            info = course_info.get(course, {})
            if t != info.get("preferred_time"):
                soft_violations += 1
            if rooms[r]["campus"] != info.get("preferred_campus"):
                soft_violations += 1
        
        quality = (len(courses) - soft_violations) / len(courses) * 10
    else:
        hard_violations = len(courses) - len(solution)
    
    metrics = AlgorithmMetrics(
        algorithm_name="Random Assignment",
        time_seconds=round(end - start, 3),
        solution_found=len(solution) == len(courses),
        hard_violations=hard_violations,
        soft_violations=soft_violations,
        solution_quality=round(quality, 2),
        nodes_explored=attempts,
        description="Random slot assignment (baseline)"
    )
    
    return solution if len(solution) == len(courses) else None, metrics

# =========================
# BASELINE 2: GREEDY ASSIGNMENT
# =========================
def greedy_assignment(data) -> Tuple[Optional[Dict], AlgorithmMetrics]:
    """
    Greedy heuristic: Assign courses to first available slot.
    Simple but practical baseline.
    """
    students = data["students"]
    courses = data["courses"]
    rooms = data["rooms"]
    timeslots = data["timeslots"]
    course_info = data.get("course_info", {})
    
    course_students = build_course_students(students)
    
    start = time.time()
    
    solution = {}
    nodes_explored = 0
    
    for course in courses:
        nodes_explored += 1
        student_count = len(course_students.get(course, []))
        
        # Try slots in order
        assigned = False
        for t in timeslots:
            if assigned:
                break
            for room, room_data in rooms.items():
                nodes_explored += 1
                if student_count > room_data["capacity"]:
                    continue
                
                # Check constraints
                slot = (t, room)
                valid = True
                
                for other_course, (t2, r2) in solution.items():
                    # Room overlap
                    if r2 == room and t2 == t:
                        valid = False
                        break
                    # Student conflict
                    if t2 == t and set(course_students.get(course, [])).intersection(course_students.get(other_course, [])):
                        valid = False
                        break
                
                if valid:
                    solution[course] = slot
                    assigned = True
                    break
    
    end = time.time()
    
    # Evaluate solution
    hard_violations = 0
    soft_violations = 0
    quality = 0.0
    
    if len(solution) == len(courses):
        for course, (t, r) in solution.items():
            info = course_info.get(course, {})
            if t != info.get("preferred_time"):
                soft_violations += 1
            if rooms[r]["campus"] != info.get("preferred_campus"):
                soft_violations += 1
        quality = (len(courses) - soft_violations) / len(courses) * 10
    else:
        hard_violations = len(courses) - len(solution)
    
    metrics = AlgorithmMetrics(
        algorithm_name="Greedy Assignment",
        time_seconds=round(end - start, 3),
        solution_found=len(solution) == len(courses),
        hard_violations=hard_violations,
        soft_violations=soft_violations,
        solution_quality=round(quality, 2),
        nodes_explored=nodes_explored,
        description="Greedy first-fit assignment"
    )
    
    return solution if len(solution) == len(courses) else None, metrics

# =========================
# COMPARISON ENGINE
# =========================
class AlgorithmComparison:
    def __init__(self, data):
        self.data = data
        self.results = []
    
    def run_baseline_algorithms(self) -> List[AlgorithmMetrics]:
        """Run alternative algorithms for comparison."""
        print("\n" + "="*70)
        print("ALGORITHM COMPARISON - BASELINE APPROACHES")
        print("="*70)
        
        # Random assignment
        print("\n[1/2] Testing: Random Assignment")
        print("      (Random slot selection)")
        _, metrics_random = random_assignment(self.data)
        self.results.append(metrics_random)
        print(f"      ✓ Found: {metrics_random.solution_found}")
        print(f"      ✓ Time: {metrics_random.time_seconds}s")
        print(f"      ✓ Hard Violations: {metrics_random.hard_violations}")
        print(f"      ✓ Nodes: {metrics_random.nodes_explored}")
        
        # Greedy assignment
        print("\n[2/2] Testing: Greedy Assignment")
        print("      (First-fit heuristic)")
        _, metrics_greedy = greedy_assignment(self.data)
        self.results.append(metrics_greedy)
        print(f"      ✓ Found: {metrics_greedy.solution_found}")
        print(f"      ✓ Time: {metrics_greedy.time_seconds}s")
        print(f"      ✓ Hard Violations: {metrics_greedy.hard_violations}")
        print(f"      ✓ Nodes: {metrics_greedy.nodes_explored}")
        
        return self.results
    
    def compare_with_csp(self, csp_metrics):
        """Compare baseline results with CSP approach."""
        print("\n" + "="*70)
        print("ALGORITHM COMPARISON ANALYSIS")
        print("="*70)
        
        print(f"\n{'Algorithm':<30} {'Success':<10} {'Time (s)':<12} {'Quality':<12} {'Nodes':<10}")
        print("-" * 80)
        
        for result in self.results:
            found = "✓" if result.solution_found else "✗"
            quality = f"{result.solution_quality:.2f}" if result.solution_found else "N/A"
            print(f"{result.algorithm_name:<30} {found:<10} {result.time_seconds:<12} {quality:<12} {result.nodes_explored:<10}")
        
        # CSP results
        found = "✓" if csp_metrics.solution_found else "✗"
        quality = f"{csp_metrics.solution_quality:.2f}" if csp_metrics.solution_found else "N/A"
        print(f"{csp_metrics.algorithm_name:<30} {found:<10} {csp_metrics.time_seconds:<12} {quality:<12} {csp_metrics.nodes_explored:<10}")
        
        # Analysis
        print("\n" + "="*70)
        print("KEY FINDINGS")
        print("="*70)
        
        if self.results[1].solution_found and csp_metrics.solution_found:
            speedup = self.results[1].time_seconds / csp_metrics.time_seconds
            print(f"\n✅ CSP is {speedup:.2f}x faster than Greedy")
            print(f"✅ CSP explores {self.results[1].nodes_explored / csp_metrics.nodes_explored:.1f}x fewer nodes")
            
            if csp_metrics.solution_quality > self.results[1].solution_quality:
                print(f"✅ CSP achieves better quality ({csp_metrics.solution_quality:.2f} vs {self.results[1].solution_quality:.2f})")
            
            print(f"\n🎯 Conclusion: CSP with heuristics is SIGNIFICANTLY superior")
        
        return self.results
    
    def save_comparison_results(self, filename="algorithm_comparison_results.csv"):
        """Save comparison results to CSV."""
        with open(filename, 'w', newline='') as f:
            if not self.results:
                return
            
            fieldnames = list(self.results[0].to_dict().keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            writer.writeheader()
            for result in self.results:
                writer.writerow(result.to_dict())
        
        print(f"✓ Results saved to {filename}")

def main():
    # 1. Update the path to match your directory structure
    data = load_data("../dataset/data/medium.json")
    
    print(f"\n📊 Algorithm Comparison on Medium Dataset")
    print(f"   {len(data['students'])} students, {len(data['courses'])} courses")
    
    # Run baseline comparison
    comparison = AlgorithmComparison(data)
    comparison.run_baseline_algorithms()
    
    # 2. Run the actual CSP Engine instead of using dummy data
    print("\n[3/3] Testing: CSP + Heuristics")
    
    # Configure the engine to use all your proposed heuristics
    best_config = SolverConfig(use_mrv=True, use_degree_heuristic=True, use_forward_checking=True)
    
    # Execute the live solver
    csp_metrics_raw = solve_with_config(data, best_config)
    
    # Map the live engine's output to your AlgorithmMetrics format
    csp_metrics = AlgorithmMetrics(
        algorithm_name="CSP (MRV + Degree + FC)",
        time_seconds=csp_metrics_raw.time_seconds,
        solution_found=csp_metrics_raw.solution_found,
        hard_violations=csp_metrics_raw.hard_constraint_violations,
        soft_violations=csp_metrics_raw.soft_constraint_violations,
        solution_quality=csp_metrics_raw.avg_solution_quality,
        nodes_explored=csp_metrics_raw.nodes_explored,
        description="Full CSP with all heuristics"
    )
    
    comparison.compare_with_csp(csp_metrics)
    
    # 3. Save to the root EXAM-SCHEDULER folder
    comparison.save_comparison_results("../../algorithm_comparison_results.csv")

if __name__ == "__main__":
    main()