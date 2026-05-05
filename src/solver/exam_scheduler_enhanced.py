import json
import time
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, asdict
import statistics

# =========================
# DATA STRUCTURES & METRICS
# =========================
@dataclass
class SolverConfig:
    #Configuration for solver heuristics and soft constraint weights.
    use_mrv: bool = True
    use_degree_heuristic: bool = True
    use_forward_checking: bool = True
    
    # Soft constraint weights
    time_preference_weight: float = 10.0
    campus_preference_weight: float = 10.0
    back_to_back_penalty: float = 5.0

    max_time_seconds: float = 30 # Time limit for solving (can be used to implement a timeout in backtracking)
    
    def name(self) -> str:
        #Generate descriptive name for this configuration.
        parts = []
        if self.use_mrv:
            parts.append("MRV")
        if self.use_degree_heuristic:
            parts.append("Degree")
        if self.use_forward_checking:
            parts.append("FC")
        
        config_name = "+".join(parts) if parts else "Basic"
        
        # Include soft constraint info
        soft_name = f"SC({self.time_preference_weight:.0f},{self.campus_preference_weight:.0f},{self.back_to_back_penalty:.0f})"
        return f"{config_name}_{soft_name}"

@dataclass
class SolverMetrics:
    #Metrics collected during solving.
    config_name: str
    solution_found: bool
    nodes_explored: int
    time_seconds: float
    soft_constraint_violations: int = 0
    hard_constraint_violations: int = 0
    avg_solution_quality: float = 0.0  # Higher is better
    solution: Optional[Dict] = None
    
    def to_dict(self):
        #Convert to dict, excluding the full solution for CSV output.
        d = asdict(self)
        d.pop('solution', None)
        return d

# =========================
# LOAD & PREPROCESS DATA
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

def build_conflict_graph(courses, course_students):
    #Builds an adjacency list of courses that share students.
    graph = {c: set() for c in courses}
    for c1 in courses:
        for c2 in courses:
            if c1 != c2 and share_students(course_students, c1, c2):
                graph[c1].add(c2)
    return graph

def build_domain(courses, timeslots, rooms, course_students):
    domain = {}
    max_cap = max(room_data["capacity"] for room_data in rooms.values())

    for course in courses:
        domain[course] = []
        student_count = len(course_students.get(course, []))

        # If no room can fit all students, use rooms with largest capacity
        # (treat capacity as a soft constraint to keep domain non-empty)
        if student_count > max_cap:
            eligible_rooms = [r for r, rd in rooms.items() if rd["capacity"] == max_cap]
        else:
            eligible_rooms = [r for r, rd in rooms.items() if student_count <= rd["capacity"]]

        for t in timeslots:
            for room in eligible_rooms:
                domain[course].append((t, room))
    return domain

# =========================
# HELPER FUNCTIONS
# =========================
def build_conflict_sets(course_students):
    """Precompute set of shared students between every pair of courses for O(1) lookup."""
    conflict_sets = {}
    courses = list(course_students.keys())
    for c in courses:
        conflict_sets[c] = set(course_students.get(c, []))
    return conflict_sets

def share_students_fast(conflict_sets, c1, c2):
    s1 = conflict_sets.get(c1, set())
    s2 = conflict_sets.get(c2, set())
    return not s1.isdisjoint(s2)

def get_slot_index(timeslots, t):
    try:
        return timeslots.index(t)
    except ValueError:
        return -1

def same_day(t1, t2):
    """Check if two timeslots are on the same day."""
    d1 = t1.split("_")[0] if "_" in t1 else t1
    d2 = t2.split("_")[0] if "_" in t2 else t2
    return d1 == d2

def share_students(course_students, c1, c2):
    if c1 not in course_students or c2 not in course_students:
        return False
    return not set(course_students[c1]).isdisjoint(course_students[c2])

# =========================
# CONSTRAINT CHECK (HARD)
# =========================
# In solver/exam_scheduler_enhanced.py

def is_consistent(course, value, assignment, course_students, rooms, timeslots, conflict_sets=None):
    t1, r1 = value
    for c2, (t2, r2) in assignment.items():
        # Hard Constraint: Student conflict (Same student can't be in two places at once)
        has_conflict = (share_students_fast(conflict_sets, course, c2)
                        if conflict_sets else share_students(course_students, course, c2))
        if has_conflict:
            if t1 == t2:
                return False
            
            # Travel constraint: students need at least 1 gap slot between
            # exams on different campuses
            campus1 = rooms[r1]["campus"]
            campus2 = rooms[r2]["campus"]
            if campus1 != campus2:
                if abs(get_slot_index(timeslots, t1) - get_slot_index(timeslots, t2)) < 2:
                    return False
                    
        # Hard Constraint: Room overlap (Two exams can't be in the same room at the same time)
        if r1 == r2 and t1 == t2:
            return False
    return True

# =========================
# HEURISTICS
# =========================
def is_consistent_pair(c1, val1, c2, val2, course_students, rooms, timeslots, conflict_sets=None):
    t1, r1 = val1
    t2, r2 = val2

    # Student conflict
    has_conflict = (share_students_fast(conflict_sets, c1, c2)
                    if conflict_sets else share_students(course_students, c1, c2))
    if has_conflict:
        if t1 == t2:
            return False

        # Travel constraint
        if rooms[r1]["campus"] != rooms[r2]["campus"]:
            if abs(get_slot_index(timeslots, t1) - get_slot_index(timeslots, t2)) < 2:
                return False

    # Room conflict
    if r1 == r2 and t1 == t2:
        return False

    return True

def select_variable(assignment, domain, courses, conflict_graph, config: SolverConfig):
    # Variable selection with configurable heuristics.
    unassigned = [c for c in courses if c not in assignment]
    
    if not unassigned:
        return None

    # Fail-fast: if any unassigned variable has an empty domain, return it
    # so the backtracker immediately sees no valid values and backtracks.
    for v in unassigned:
        if len(domain[v]) == 0:
            return v

    #  No heuristics → simple
    if not config.use_mrv:
        return unassigned[0]

    # MRV: pick smallest domain
    min_domain_size = min(len(domain[v]) for v in unassigned)

    candidates = []
    for v in unassigned:
        if len(domain[v]) == min_domain_size:
            candidates.append(v)

    # If no degree heuristic → return first MRV
    if not config.use_degree_heuristic:
        return candidates[0]

    # Degree heuristic: pick most constrained variable
    best = None
    max_degree = -1

    for v in candidates:
        degree = len(conflict_graph[v])
        if degree > max_degree:
            max_degree = degree
            best = v

    return best
    

def order_domain_values(var, domain, assignment, course_info, course_students, timeslots, rooms, conflict_graph, config: SolverConfig, conflict_sets=None):
    # Value ordering with soft constraints + LCV (LCV only when forward checking is on)

    info = course_info.get(var, {})
    pref_time = info.get("preferred_time")
    pref_campus = info.get("preferred_campus")

    values = domain[var]

    # If not using FC, skip expensive LCV and just apply soft constraint preferences
    if not config.use_forward_checking:
        def simple_score(value):
            t, r = value
            s = 0
            if pref_time and t == pref_time:
                s -= 5
            if pref_campus and rooms[r]["campus"] == pref_campus:
                s -= 3
            return s
        return sorted(values, key=simple_score)

    def score(value):
        t, r = value
        s = 0

        # Soft constraints
        if pref_time and t == pref_time:
            s -= 5
        if pref_campus and rooms[r]["campus"] == pref_campus:
            s -= 3

        # LCV: count how many options this blocks for others
        conflict_penalty = 0
        for neighbor in conflict_graph[var]:
            if neighbor in assignment:
                continue
            for val in domain[neighbor]:
                if not is_consistent_pair(var, value, neighbor, val, course_students, rooms, timeslots, conflict_sets):
                    conflict_penalty += 1
        s += conflict_penalty
        return s

    # lower score = better
    return sorted(values, key=score)

# =========================
# FORWARD CHECKING
# =========================
def forward_check(course, value, domain, assignment, course_students, rooms, timeslots, conflict_graph, config: SolverConfig, conflict_sets=None):
    if not config.use_forward_checking:
        return domain  # Skip forward checking if disabled
    
    new_domain = {c: vals[:] for c, vals in domain.items()}
    t1, r1 = value
    campus1 = rooms[r1]["campus"]
    idx1 = get_slot_index(timeslots, t1)

    for neighbor in conflict_graph[course]:
        if neighbor in assignment:
            continue

        valid_values = []
        for val in new_domain[neighbor]:
            t2, r2 = val
            # Check against newly assigned course
            has_conflict = share_students_fast(conflict_sets, neighbor, course) if conflict_sets else share_students(course_students, neighbor, course)
            if has_conflict:
                if t1 == t2:
                    continue
                if campus1 != rooms[r2]["campus"]:
                    if abs(idx1 - get_slot_index(timeslots, t2)) < 2:
                        continue
            if r1 == r2 and t1 == t2:
                continue
            # Check against rest of assignment
            if is_consistent(neighbor, val, assignment, course_students, rooms, timeslots, conflict_sets):
                valid_values.append(val)
        
        if not valid_values:
            return None
            
        new_domain[neighbor] = valid_values
    return new_domain

# =========================
# SOLUTION QUALITY ANALYSIS
# =========================
def analyze_solution_quality(solution, assignment, course_students, rooms, timeslots, course_info, config: SolverConfig):
    #Calculate soft constraint satisfaction and quality metrics.
    if not solution:
        return 0, 0
    
    soft_violations = 0
    hard_violations = 0
    quality_score = 0
    
    for course, (t, r) in solution.items():
        info = course_info.get(course, {})
        pref_time = info.get("preferred_time")
        pref_campus = info.get("preferred_campus")
        campus = rooms[r]["campus"]
        
        # Quality improvements
        if t == pref_time:
            quality_score += config.time_preference_weight
        else:
            soft_violations += 1
            
        if campus == pref_campus:
            quality_score += config.campus_preference_weight
        else:
            soft_violations += 1
        
        # Back-to-back penalty
        val_idx = get_slot_index(timeslots, t)
        for c2, (t2, r2) in solution.items():
            if course != c2 and share_students(course_students, course, c2):
                t2_idx = get_slot_index(timeslots, t2)
                if rooms[r2]["campus"] == campus and abs(val_idx - t2_idx) == 1:
                    soft_violations += 1
                    quality_score -= config.back_to_back_penalty
    
    return soft_violations, quality_score

# =========================
# BACKTRACKING
# =========================
def backtrack(assignment, domain, courses, course_students, rooms, timeslots, stats, conflict_graph, course_info, config: SolverConfig, start_time, conflict_sets=None):
    stats["nodes"] += 1

    if time.time() - start_time > config.max_time_seconds:
        return None

    if len(assignment) == len(courses):
        return assignment

    var = select_variable(assignment, domain, courses, conflict_graph, config)
    if var is None:
        return assignment
    
    ordered_values = order_domain_values(var, domain, assignment, course_info, course_students, timeslots, rooms, conflict_graph, config, conflict_sets)

    for value in ordered_values:
        if is_consistent(var, value, assignment, course_students, rooms, timeslots, conflict_sets):
            new_assignment = assignment.copy()
            new_assignment[var] = value

            new_domain = forward_check(
                var, value, domain, new_assignment,
                course_students, rooms, timeslots, conflict_graph, config, conflict_sets
            )

            if new_domain is not None:
                result = backtrack(
                    new_assignment, new_domain, courses,
                    course_students, rooms, timeslots, stats, conflict_graph, course_info, config, start_time, conflict_sets
                )

                if result is not None:
                    return result

    return None

# =========================
# MAIN SOLVER WRAPPER
# =========================
def solve_with_config(data, config: SolverConfig) -> SolverMetrics:
    #Solve exam scheduling with a specific configuration.
    students = data["students"]
    courses = data["courses"]
    rooms = data["rooms"]
    timeslots = data["timeslots"]
    course_info = data.get("course_info", {})

    course_students = build_course_students(students)
    conflict_graph = build_conflict_graph(courses, course_students)
    conflict_sets = build_conflict_sets(course_students)
    domain = build_domain(courses, timeslots, rooms, course_students)

    # Increase time limit for configs without forward checking
    effective_config = config
    if not config.use_forward_checking:
        from dataclasses import replace
        effective_config = SolverConfig(
            use_mrv=config.use_mrv,
            use_degree_heuristic=config.use_degree_heuristic,
            use_forward_checking=config.use_forward_checking,
            time_preference_weight=config.time_preference_weight,
            campus_preference_weight=config.campus_preference_weight,
            back_to_back_penalty=config.back_to_back_penalty,
            max_time_seconds=60.0,
        )

    stats = {"nodes": 0}
    start = time.time()

    solution = backtrack(
        {}, domain, courses,
        course_students, rooms, timeslots, stats, conflict_graph, course_info, effective_config, start, conflict_sets
    )

    end = time.time()

    # Analyze solution
    soft_violations, quality_score = analyze_solution_quality(
        solution, {}, course_students, rooms, timeslots, course_info, config
    ) if solution else (0, 0)
    
    avg_quality = quality_score / len(courses) if solution and len(courses) > 0 else 0.0

    metrics = SolverMetrics(
        config_name=config.name(),
        solution_found=solution is not None,
        nodes_explored=stats["nodes"],
        time_seconds=round(end - start, 3),
        soft_constraint_violations=soft_violations,
        avg_solution_quality=round(avg_quality, 2),
        solution=solution
    )

    return metrics

# =========================
# COMPARISON ENGINE
# =========================
class ExamSchedulerComparison:
    def __init__(self, data):
        self.data = data
        self.results = []
    
    def run_heuristic_comparison(self) -> List[SolverMetrics]:
        #Compare different heuristic combinations (Option A).
        print("\n" + "="*70)
        print("HEURISTIC IMPACT ANALYSIS")
        print("="*70)
        
        configs = [
            SolverConfig(use_mrv=False, use_degree_heuristic=False, use_forward_checking=False),
            SolverConfig(use_mrv=True, use_degree_heuristic=False, use_forward_checking=False),
            SolverConfig(use_mrv=True, use_degree_heuristic=True, use_forward_checking=False),
            SolverConfig(use_mrv=True, use_degree_heuristic=True, use_forward_checking=True),
        ]
        
        results = []
        for i, config in enumerate(configs, 1):
            print(f"\n[{i}/4] Running: {config.name()}")
            print(f"     MRV={config.use_mrv}, Degree={config.use_degree_heuristic}, FC={config.use_forward_checking}")
            
            metrics = solve_with_config(self.data, config)
            results.append(metrics)
            
            print(f"     Solution Found: {metrics.solution_found}")
            print(f"     Time: {metrics.time_seconds}s | Nodes: {metrics.nodes_explored}")
            print(f"     Quality: {metrics.avg_solution_quality} | Soft Violations: {metrics.soft_constraint_violations}")
        
        self.results.extend(results)
        return results
    
    def run_soft_constraint_analysis(self) -> List[SolverMetrics]:
        #Compare different soft constraint weight configurations (Option B).
        print("\n" + "="*70)
        print("SOFT CONSTRAINT TRADE-OFF ANALYSIS")
        print("="*70)
        
        # Base config: full heuristics
        base_config = SolverConfig(use_mrv=True, use_degree_heuristic=True, use_forward_checking=True)
        
        # Test different "softness" levels (weight multipliers)
        softness_levels = [
            (0.0, "No Soft Constraints"),      # Ignore preferences
            (0.5, "Low Weight"),               # Half weights
            (1.0, "Standard Weight"),          # Default
            (2.0, "High Weight"),              # Double weights
        ]
        
        results = []
        for i, (multiplier, label) in enumerate(softness_levels, 1):
            config = SolverConfig(
                use_mrv=True,
                use_degree_heuristic=True,
                use_forward_checking=True,
                time_preference_weight=10.0 * multiplier,
                campus_preference_weight=10.0 * multiplier,
                back_to_back_penalty=5.0 * multiplier,
            )
            
            print(f"\n[{i}/4] Running: {label} (multiplier={multiplier})")
            
            metrics = solve_with_config(self.data, config)
            results.append(metrics)
            
            print(f"     Solution Found: {metrics.solution_found}")
            print(f"     Time: {metrics.time_seconds}s | Nodes: {metrics.nodes_explored}")
            print(f"     Quality: {metrics.avg_solution_quality} | Soft Violations: {metrics.soft_constraint_violations}")
        
        self.results.extend(results)
        return results
    
    def run_all_comparisons(self):
        #Run both Option A and Option B.
        self.run_heuristic_comparison()
        self.run_soft_constraint_analysis()
    
    def generate_analysis_report(self):
        #Generate comprehensive analysis and findings.
        print("\n" + "="*70)
        print("COMPREHENSIVE ANALYSIS REPORT")
        print("="*70)
        
        if not self.results:
            print("No results to analyze")
            return
        
        # Success rate
        successful = sum(1 for r in self.results if r.solution_found)
        print(f"\nSolution Success Rate: {successful}/{len(self.results)} ({100*successful/len(self.results):.1f}%)")
        
        # Time analysis
        successful_results = [r for r in self.results if r.solution_found]
        if successful_results:
            times = [r.time_seconds for r in successful_results]
            print(f"\nTiming Analysis (successful solutions only):")
            print(f"  Min: {min(times):.3f}s")
            print(f"  Max: {max(times):.3f}s")
            print(f"  Mean: {statistics.mean(times):.3f}s")
            if len(times) > 1:
                print(f"  Median: {statistics.median(times):.3f}s")
            
            # Speed improvement
            baseline = successful_results[0].time_seconds
            print(f"\nSpeed Improvement vs. Baseline:")
            for r in successful_results[1:]:
                improvement = ((baseline - r.time_seconds) / baseline * 100)
                print(f"  {r.config_name}: {improvement:+.1f}%")
        
        # Node exploration analysis
        if successful_results:
            nodes = [r.nodes_explored for r in successful_results]
            print(f"\nNode Exploration (successful solutions only):")
            print(f"  Min: {min(nodes)}")
            print(f"  Max: {max(nodes)}")
            print(f"  Mean: {statistics.mean(nodes):.0f}")
            
            baseline = successful_results[0].nodes_explored
            print(f"\nNode Reduction vs. Baseline:")
            for r in successful_results[1:]:
                reduction = ((baseline - r.nodes_explored) / baseline * 100)
                print(f"  {r.config_name}: {reduction:+.1f}%")
        
        # Quality analysis
        if successful_results:
            qualities = [r.avg_solution_quality for r in successful_results]
            print(f"\nSolution Quality (avg score per course):")
            for r in successful_results:
                print(f"  {r.config_name}: {r.avg_solution_quality:.2f}")
        
        print("\n" + "="*70)
    
    def save_results_csv(self, filename="comparison_results.csv"):
        """Save results to CSV for easy analysis in Excel/plotting."""
        import csv
        
        with open(filename, 'w', newline='') as f:
            if not self.results:
                print("No results to save")
                return
            
            fieldnames = list(self.results[0].to_dict().keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            writer.writeheader()
            for result in self.results:
                writer.writerow(result.to_dict())
        
        print(f"\n✓ Results saved to {filename}")
    
    def save_results_json(self, filename="comparison_results.json"):
        #Save detailed results including full solutions.
        results_data = {
            "summary": {
                "total_configs": len(self.results),
                "successful": sum(1 for r in self.results if r.solution_found),
            },
            "results": [
                {
                    **asdict(r),
                    "solution": r.solution if r.solution else None
                }
                for r in self.results
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        print(f"✓ Detailed results saved to {filename}")

# =========================
# MAIN ENTRY POINT
# =========================
def main():
    # Load your medium.json dataset
    data = load_data("../dataset/data/medium.json")
    print(f"\n Dataset: {len(data['students'])} students, {len(data['courses'])} courses, {len(data['rooms'])} rooms")
    print(f" Timeslots: {len(data['timeslots'])} slots/day |  Campuses: {len(set(r['campus'] for r in data['rooms'].values()))}")
    
    # Create comparison engine
    comparison = ExamSchedulerComparison(data)
    
    # Run both analysis types
    comparison.run_all_comparisons()
    
    # Generate report and save results
    comparison.generate_analysis_report()
    comparison.save_results_csv("../../comparison_results.csv")
    comparison.save_results_json("../../comparison_results.json")

if __name__ == "__main__":
    main()