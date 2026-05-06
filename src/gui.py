"""
Exam Scheduler CSP - Streamlit GUI
Run with: streamlit run app.py
Place this file inside the src/ folder (same level as solver/, analysis/, dataset/)
"""

import streamlit as st
import json
import time
import random
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional

# ─────────────────────────────────────────────
# ── Inline solver (no imports needed) ────────
# ─────────────────────────────────────────────

@dataclass
class SolverConfig:
    use_mrv: bool = True
    use_degree_heuristic: bool = True
    use_forward_checking: bool = True
    time_preference_weight: float = 10.0
    campus_preference_weight: float = 10.0
    back_to_back_penalty: float = 5.0
    max_time_seconds: float = 15.0

    def name(self):
        parts = []
        if self.use_mrv:
            parts.append("MRV")
        if self.use_degree_heuristic:
            parts.append("Degree")
        if self.use_forward_checking:
            parts.append("FC")
        config_name = "+".join(parts) if parts else "Basic"
        sc = f"SC({self.time_preference_weight:.0f},{self.campus_preference_weight:.0f},{self.back_to_back_penalty:.0f})"
        return f"{config_name}_{sc}"


@dataclass
class SolverMetrics:
    config_name: str
    solution_found: bool
    nodes_explored: int
    time_seconds: float
    soft_constraint_violations: int = 0
    hard_constraint_violations: int = 0
    avg_solution_quality: float = 0.0
    solution: Optional[Dict] = None

    def to_dict(self):
        d = asdict(self)
        d.pop("solution", None)
        return d


# ── helpers ──────────────────────────────────

def build_course_students(students):
    cs = {}
    for sid, info in students.items():
        for c in info["courses"]:
            cs.setdefault(c, []).append(sid)
    return cs


def build_conflict_graph(courses, course_students):
    graph = {c: set() for c in courses}
    for c1 in courses:
        s1 = set(course_students.get(c1, []))
        for c2 in courses:
            if c1 != c2 and not s1.isdisjoint(course_students.get(c2, [])):
                graph[c1].add(c2)
    return graph


def build_conflict_sets(course_students):
    return {c: set(course_students.get(c, [])) for c in course_students}


def build_domain(courses, timeslots, rooms, course_students):
    domain = {}
    max_cap = max(rd["capacity"] for rd in rooms.values())
    for course in courses:
        sc = len(course_students.get(course, []))
        eligible = [r for r, rd in rooms.items() if rd["capacity"] >= sc] or \
                   [r for r, rd in rooms.items() if rd["capacity"] == max_cap]
        domain[course] = [(t, r) for t in timeslots for r in eligible]
    return domain


def share_students_fast(conflict_sets, c1, c2):
    return not conflict_sets.get(c1, set()).isdisjoint(conflict_sets.get(c2, set()))


def get_slot_index(timeslots, t):
    try:
        return timeslots.index(t)
    except ValueError:
        return -1


def is_consistent(course, value, assignment, rooms, timeslots, conflict_sets):
    t1, r1 = value
    idx1 = get_slot_index(timeslots, t1)
    campus1 = rooms[r1]["campus"]
    for c2, (t2, r2) in assignment.items():
        if share_students_fast(conflict_sets, course, c2):
            if t1 == t2:
                return False
            if campus1 != rooms[r2]["campus"]:
                if abs(idx1 - get_slot_index(timeslots, t2)) < 2:
                    return False
        if r1 == r2 and t1 == t2:
            return False
    return True


def select_variable(assignment, domain, courses, conflict_graph, config):
    unassigned = [c for c in courses if c not in assignment]
    if not unassigned:
        return None
    for v in unassigned:
        if len(domain[v]) == 0:
            return v
    if not config.use_mrv:
        return unassigned[0]
    min_d = min(len(domain[v]) for v in unassigned)
    candidates = [v for v in unassigned if len(domain[v]) == min_d]
    if not config.use_degree_heuristic:
        return candidates[0]
    return max(candidates, key=lambda v: len(conflict_graph[v]))


def order_domain_values(var, domain, assignment, course_info, rooms, timeslots,
                        conflict_graph, config, conflict_sets):
    info = course_info.get(var, {})
    pref_t = info.get("preferred_time")
    pref_c = info.get("preferred_campus")
    values = domain[var]

    if not config.use_forward_checking:
        def s(val):
            t, r = val
            score = 0
            if pref_t and t == pref_t: score -= 5
            if pref_c and rooms[r]["campus"] == pref_c: score -= 3
            return score
        return sorted(values, key=s)

    def score(val):
        t, r = val
        s = 0
        if pref_t and t == pref_t: s -= 5
        if pref_c and rooms[r]["campus"] == pref_c: s -= 3
        for nb in conflict_graph[var]:
            if nb in assignment:
                continue
            for nv in domain[nb]:
                t2, r2 = nv
                if share_students_fast(conflict_sets, var, nb):
                    if t == t2: s += 1; continue
                    if rooms[r]["campus"] != rooms[r2]["campus"]:
                        if abs(get_slot_index(timeslots, t) - get_slot_index(timeslots, t2)) < 2:
                            s += 1; continue
                if r == r2 and t == t2: s += 1
        return s

    return sorted(values, key=score)


def forward_check(course, value, domain, assignment, rooms, timeslots,
                  conflict_graph, config, conflict_sets):
    if not config.use_forward_checking:
        return domain
    new_domain = {c: vals[:] for c, vals in domain.items()}
    t1, r1 = value
    idx1 = get_slot_index(timeslots, t1)
    campus1 = rooms[r1]["campus"]
    for nb in conflict_graph[course]:
        if nb in assignment:
            continue
        valid = []
        for val in new_domain[nb]:
            t2, r2 = val
            if share_students_fast(conflict_sets, nb, course):
                if t1 == t2: continue
                if campus1 != rooms[r2]["campus"]:
                    if abs(idx1 - get_slot_index(timeslots, t2)) < 2: continue
            if r1 == r2 and t1 == t2: continue
            if is_consistent(nb, val, assignment, rooms, timeslots, conflict_sets):
                valid.append(val)
        if not valid:
            return None
        new_domain[nb] = valid
    return new_domain


def backtrack(assignment, domain, courses, rooms, timeslots, stats,
              conflict_graph, course_info, config, start_time, conflict_sets):
    stats["nodes"] += 1
    if time.time() - start_time > config.max_time_seconds:
        return None
    if len(assignment) == len(courses):
        return assignment
    var = select_variable(assignment, domain, courses, conflict_graph, config)
    if var is None:
        return assignment
    ordered = order_domain_values(var, domain, assignment, course_info, rooms,
                                  timeslots, conflict_graph, config, conflict_sets)
    for value in ordered:
        if is_consistent(var, value, assignment, rooms, timeslots, conflict_sets):
            new_asgn = {**assignment, var: value}
            new_dom = forward_check(var, value, domain, new_asgn, rooms, timeslots,
                                    conflict_graph, config, conflict_sets)
            if new_dom is not None:
                result = backtrack(new_asgn, new_dom, courses, rooms, timeslots,
                                   stats, conflict_graph, course_info, config,
                                   start_time, conflict_sets)
                if result is not None:
                    return result
    return None


def analyze_quality(solution, rooms, timeslots, course_info, config):
    if not solution:
        return 0, 0.0
    sv, qs = 0, 0.0
    for course, (t, r) in solution.items():
        info = course_info.get(course, {})
        if t == info.get("preferred_time"):
            qs += config.time_preference_weight
        else:
            sv += 1
        if rooms[r]["campus"] == info.get("preferred_campus"):
            qs += config.campus_preference_weight
        else:
            sv += 1
    return sv, qs


def solve_with_config(data, config: SolverConfig) -> SolverMetrics:
    students = data["students"]
    courses = data["courses"]
    rooms = data["rooms"]
    timeslots = data["timeslots"]
    course_info = data.get("course_info", {})

    cs = build_course_students(students)
    cg = build_conflict_graph(courses, cs)
    conflict_sets = build_conflict_sets(cs)
    domain = build_domain(courses, timeslots, rooms, cs)

    eff = SolverConfig(
        use_mrv=config.use_mrv,
        use_degree_heuristic=config.use_degree_heuristic,
        use_forward_checking=config.use_forward_checking,
        time_preference_weight=config.time_preference_weight,
        campus_preference_weight=config.campus_preference_weight,
        back_to_back_penalty=config.back_to_back_penalty,
        max_time_seconds=config.max_time_seconds if config.use_forward_checking else 15.0,
    )

    stats = {"nodes": 0}
    start = time.time()
    solution = backtrack({}, domain, courses, rooms, timeslots, stats,
                         cg, course_info, eff, start, conflict_sets)
    elapsed = round(time.time() - start, 3)

    sv, qs = analyze_quality(solution, rooms, timeslots, course_info, config)
    avg_q = round(qs / len(courses), 2) if solution and len(courses) > 0 else 0.0

    return SolverMetrics(
        config_name=config.name(),
        solution_found=solution is not None,
        nodes_explored=stats["nodes"],
        time_seconds=elapsed,
        soft_constraint_violations=sv,
        avg_solution_quality=avg_q,
        solution=solution,
    )


# ── Baselines ─────────────────────────────────

def random_assignment(data):
    students = data["students"]
    courses = data["courses"]
    rooms = data["rooms"]
    timeslots = data["timeslots"]
    course_info = data.get("course_info", {})
    cs = build_course_students(students)
    start = time.time()
    solution = {}
    attempts = 0
    while len(solution) < len(courses) and attempts < 1000:
        attempts += 1
        course = random.choice([c for c in courses if c not in solution])
        slot = (random.choice(timeslots), random.choice(list(rooms.keys())))
        valid = True
        for oc, (t2, r2) in solution.items():
            if slot[0] == t2 and slot[1] == r2:
                valid = False; break
            if slot[0] == t2 and not set(cs.get(course, [])).isdisjoint(cs.get(oc, [])):
                valid = False; break
        if valid:
            solution[course] = slot
    elapsed = round(time.time() - start, 3)
    sv = 0
    if len(solution) == len(courses):
        for c, (t, r) in solution.items():
            info = course_info.get(c, {})
            if t != info.get("preferred_time"): sv += 1
            if rooms[r]["campus"] != info.get("preferred_campus"): sv += 1
        q = round((len(courses) - sv) / len(courses) * 10, 2)
        found = True
    else:
        q = 0.0; found = False
    return solution if found else None, SolverMetrics(
        config_name="Random Assignment",
        solution_found=found,
        nodes_explored=attempts,
        time_seconds=elapsed,
        soft_constraint_violations=sv,
        avg_solution_quality=q,
        solution=solution if found else None,
    )


def greedy_assignment(data):
    students = data["students"]
    courses = data["courses"]
    rooms = data["rooms"]
    timeslots = data["timeslots"]
    course_info = data.get("course_info", {})
    cs = build_course_students(students)
    start = time.time()
    solution = {}
    nodes = 0
    for course in courses:
        nodes += 1
        sc = len(cs.get(course, []))
        assigned = False
        for t in timeslots:
            if assigned: break
            for room, rd in rooms.items():
                nodes += 1
                if sc > rd["capacity"]: continue
                slot = (t, room)
                valid = True
                for oc, (t2, r2) in solution.items():
                    if r2 == room and t2 == t: valid = False; break
                    if t2 == t and not set(cs.get(course, [])).isdisjoint(cs.get(oc, [])):
                        valid = False; break
                if valid:
                    solution[course] = slot
                    assigned = True; break
    elapsed = round(time.time() - start, 3)
    found = len(solution) == len(courses)
    sv = 0
    if found:
        for c, (t, r) in solution.items():
            info = course_info.get(c, {})
            if t != info.get("preferred_time"): sv += 1
            if rooms[r]["campus"] != info.get("preferred_campus"): sv += 1
        q = round((len(courses) - sv) / len(courses) * 10, 2)
    else:
        q = 0.0
    return solution if found else None, SolverMetrics(
        config_name="Greedy Assignment",
        solution_found=found,
        nodes_explored=nodes,
        time_seconds=elapsed,
        soft_constraint_violations=sv,
        avg_solution_quality=q,
        solution=solution if found else None,
    )


# ─────────────────────────────────────────────
# ── Page helpers ─────────────────────────────
# ─────────────────────────────────────────────

PALETTE = {
    "primary": "#4F46E5",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger":  "#EF4444",
    "bg":      "#0F172A",
    "card":    "#1E293B",
    "text":    "#F1F5F9",
    "muted":   "#94A3B8",
}

ALGO_COLORS = {
    "Basic": "#94A3B8",
    "MRV": "#60A5FA",
    "MRV+Degree": "#A78BFA",
    "MRV+Degree+FC": "#34D399",
    "Random Assignment": "#F87171",
    "Greedy Assignment": "#FBBF24",
}


def get_algo_short(config_name: str) -> str:
    name = config_name.split("_")[0]
    return name


def load_data_cached(path: str):
    with open(path) as f:
        return json.load(f)


# ─────────────────────────────────────────────
# ── Streamlit App ─────────────────────────────
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Exam Scheduler CSP",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #0F172A; }
    [data-testid="stSidebar"] { background: #1E293B; }
    h1,h2,h3,h4 { color: #F1F5F9 !important; }
    p, li, label { color: #CBD5E1 !important; }
    .metric-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 10px;
    }
    .metric-value { font-size: 2rem; font-weight: 700; color: #F1F5F9; }
    .metric-label { font-size: 0.85rem; color: #94A3B8; margin-top: 4px; }
    .badge-success { background:#064E3B; color:#6EE7B7; border-radius:6px; padding:2px 10px; font-size:0.8rem; }
    .badge-danger  { background:#450A0A; color:#FCA5A5; border-radius:6px; padding:2px 10px; font-size:0.8rem; }
    .slot-cell {
        background:#1E293B; border:1px solid #334155; border-radius:8px;
        padding:8px 10px; margin:3px; font-size:0.78rem; color:#E2E8F0;
    }
    .slot-cell-header {
        background:#0F172A; border:1px solid #1E293B; border-radius:8px;
        padding:8px 10px; margin:3px; font-size:0.78rem;
        color:#94A3B8; font-weight:600; text-align:center;
    }
    div[data-testid="stTabs"] button { color: #94A3B8 !important; }
    div[data-testid="stTabs"] button[aria-selected="true"] { color: #A78BFA !important; border-bottom: 2px solid #A78BFA; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────
with st.sidebar:
    st.markdown("## 📅 Exam Scheduler")
    st.markdown("---")

    dataset_choice = st.selectbox(
        "Dataset",
        ["medium", "easy", "hard"],
        help="Select problem difficulty"
    )

    DATA_PATH = f"dataset/data/{dataset_choice}.json"

    try:
        data = load_data_cached(DATA_PATH)
        st.success(f"✓ {dataset_choice}.json loaded")
    except FileNotFoundError:
        st.error(f"File not found: {DATA_PATH}\nMake sure app.py is in src/")
        st.stop()

    st.markdown("---")
    st.markdown("### ⚙️ CSP Config")
    use_mrv  = st.checkbox("MRV (Min-Remaining Values)", value=True)
    use_deg  = st.checkbox("Degree Heuristic", value=True)
    use_fc   = st.checkbox("Forward Checking", value=True)
    time_lim = st.slider("Time Limit (s)", 5, 60, 20)

    st.markdown("### 🔢 Soft Weights")
    w_time   = st.slider("Time Preference", 0.0, 20.0, 10.0, 1.0)
    w_campus = st.slider("Campus Preference", 0.0, 20.0, 10.0, 1.0)
    w_b2b    = st.slider("Back-to-Back Penalty", 0.0, 10.0, 5.0, 0.5)

    st.markdown("---")
    run_csp      = st.button("▶ Run CSP", use_container_width=True, type="primary")
    run_baseline = st.button("▶ Run Baselines", use_container_width=True)
    run_all_btn  = st.button("▶ Run Full Comparison", use_container_width=True)

    st.markdown("---")
    st.caption("Intro to AI · CSP Project")


# ── Session state ─────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = []
if "last_solution" not in st.session_state:
    st.session_state.last_solution = None
if "last_config_name" not in st.session_state:
    st.session_state.last_config_name = ""


# ── Run triggers ──────────────────────────────
custom_config = SolverConfig(
    use_mrv=use_mrv,
    use_degree_heuristic=use_deg,
    use_forward_checking=use_fc,
    time_preference_weight=w_time,
    campus_preference_weight=w_campus,
    back_to_back_penalty=w_b2b,
    max_time_seconds=float(time_lim),
)

if run_csp:
    with st.spinner("Running CSP solver…"):
        m = solve_with_config(data, custom_config)
    st.session_state.results.append(m)
    if m.solution:
        st.session_state.last_solution = m.solution
        st.session_state.last_config_name = m.config_name

if run_baseline:
    with st.spinner("Running baselines…"):
        _, rm = random_assignment(data)
        _, gm = greedy_assignment(data)
    st.session_state.results.extend([rm, gm])
    for m in [rm, gm]:
        if m.solution:
            st.session_state.last_solution = m.solution
            st.session_state.last_config_name = m.config_name

if run_all_btn:
    configs = [
        SolverConfig(False, False, False, max_time_seconds=15.0),
        SolverConfig(True, False, False,  max_time_seconds=15.0),
        SolverConfig(True, True, False,   max_time_seconds=15.0),
        SolverConfig(True, True, True,    max_time_seconds=15.0),
    ]
    with st.spinner("Running all 4 CSP configs + 2 baselines…"):
        prog = st.progress(0)
        all_res = []
        total = len(configs) + 2
        for i, cfg in enumerate(configs):
            all_res.append(solve_with_config(data, cfg))
            prog.progress((i + 1) / total)
        _, rm = random_assignment(data)
        _, gm = greedy_assignment(data)
        all_res.extend([rm, gm])
        prog.progress(1.0)
    st.session_state.results.extend(all_res)
    for m in all_res:
        if m.solution:
            st.session_state.last_solution = m.solution
            st.session_state.last_config_name = m.config_name


# ─────────────────────────────────────────────
# ── Tabs ─────────────────────────────────────
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "🧪 Results",
    "📈 Charts",
    "📅 Schedule",
    "🔍 Explorer",
])


# ══════════════════════════════════════════════
# TAB 1 – OVERVIEW
# ══════════════════════════════════════════════
with tab1:
    st.markdown("## 📊 Dataset Overview")

    students = data["students"]
    courses  = data["courses"]
    rooms    = data["rooms"]
    timeslots = data["timeslots"]
    course_info = data.get("course_info", {})
    cs_map = build_course_students(students)

    # KPI row
    c1, c2, c3, c4, c5 = st.columns(5)
    def kpi(col, val, label, color="#A78BFA"):
        col.markdown(f"""
        <div class="metric-card">
          <div class="metric-value" style="color:{color}">{val}</div>
          <div class="metric-label">{label}</div>
        </div>""", unsafe_allow_html=True)

    kpi(c1, len(students), "Students", "#60A5FA")
    kpi(c2, len(courses),  "Courses",  "#A78BFA")
    kpi(c3, len(rooms),    "Rooms",    "#34D399")
    kpi(c4, len(timeslots),"Timeslots","#F59E0B")
    active_s = sum(1 for s in students.values() if s["courses"])
    kpi(c5, active_s,      "Active Students", "#F87171")

    st.markdown("---")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("### 👥 Students per Program")
        prog_count = defaultdict(int)
        for s in students.values():
            prog_count[s["program"]] += 1
        fig = px.pie(
            values=list(prog_count.values()),
            names=list(prog_count.keys()),
            color_discrete_sequence=["#60A5FA","#A78BFA","#34D399","#F59E0B"],
            hole=0.45,
        )
        fig.update_layout(paper_bgcolor="#0F172A", plot_bgcolor="#0F172A",
                          font_color="#F1F5F9", legend_font_color="#F1F5F9",
                          margin=dict(t=20,b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("### 📚 Enrollment per Course")
        enroll = {c: len(cs_map.get(c, [])) for c in courses}
        df_e = pd.DataFrame({"Course": list(enroll.keys()),
                              "Students": list(enroll.values())}).sort_values("Students", ascending=True)
        fig2 = px.bar(df_e, x="Students", y="Course", orientation="h",
                      color="Students", color_continuous_scale="Viridis")
        fig2.update_layout(paper_bgcolor="#0F172A", plot_bgcolor="#1E293B",
                           font_color="#F1F5F9", height=480,
                           margin=dict(t=20,b=20), yaxis_tickfont_size=10,
                           coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### 🏢 Room Capacities")
    room_df = pd.DataFrame([
        {"Room": r, "Capacity": rd["capacity"], "Campus": rd["campus"]}
        for r, rd in rooms.items()
    ])
    fig3 = px.bar(room_df, x="Room", y="Capacity", color="Campus",
                  color_discrete_map={"Main": "#60A5FA", "City": "#34D399"},
                  barmode="group")
    fig3.update_layout(paper_bgcolor="#0F172A", plot_bgcolor="#1E293B",
                       font_color="#F1F5F9", margin=dict(t=20,b=40),
                       xaxis_tickangle=-45)
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("### 🕐 Timeslot Distribution")
    st.markdown(f"**{len(timeslots)} slots across "
                f"{len(set(t.split('_')[0] for t in timeslots))} days**")
    slot_data = defaultdict(list)
    for t in timeslots:
        day, period = t.split("_", 1)
        slot_data[day].append(period)
    cols = st.columns(len(slot_data))
    for i, (day, periods) in enumerate(sorted(slot_data.items())):
        with cols[i]:
            st.markdown(f"**{day}**")
            for p in periods:
                st.markdown(f"<div class='slot-cell'>{p}</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════
# TAB 2 – RESULTS TABLE
# ══════════════════════════════════════════════
with tab2:
    st.markdown("## 🧪 Experiment Results")

    if not st.session_state.results:
        st.info("No results yet. Run an algorithm from the sidebar.")
    else:
        if st.button("🗑 Clear All Results"):
            st.session_state.results = []
            st.session_state.last_solution = None
            st.rerun()

        rows = []
        for m in st.session_state.results:
            short = get_algo_short(m.config_name)
            rows.append({
                "Algorithm": short,
                "Found": "✅" if m.solution_found else "❌",
                "Time (s)": m.time_seconds,
                "Nodes": m.nodes_explored,
                "Soft Violations": m.soft_constraint_violations,
                "Avg Quality": m.avg_solution_quality,
            })

        df = pd.DataFrame(rows)

        # Style
        def highlight_found(val):
            return "color: #34D399" if val == "✅" else "color: #F87171"

        styled = df.style.map(highlight_found, subset=["Found"]) \
    .format({"Time (s)": "{:.3f}", "Avg Quality": "{:.2f}"}) \
    .set_properties(**{
        "background-color": "#1E293B",
        "color": "#F1F5F9",
        "border-color": "#334155"
    })

        st.dataframe(df, use_container_width=True, height=min(400, 56 + 35 * len(rows)))

        # Best result highlight
        successful = [m for m in st.session_state.results if m.solution_found]
        if successful:
            best = min(successful, key=lambda m: m.time_seconds)
            st.markdown("---")
            st.markdown("### 🏆 Best Result")
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Algorithm", get_algo_short(best.config_name))
            b2.metric("Time", f"{best.time_seconds}s")
            b3.metric("Nodes", f"{best.nodes_explored:,}")
            b4.metric("Quality", f"{best.avg_solution_quality:.2f}")

        # Download
        csv_data = pd.DataFrame([m.to_dict() for m in st.session_state.results]).to_csv(index=False)
        st.download_button("⬇ Download CSV", csv_data, "results.csv", "text/csv")


# ══════════════════════════════════════════════
# TAB 3 – CHARTS
# ══════════════════════════════════════════════
with tab3:
    st.markdown("## 📈 Visual Comparison")

    if not st.session_state.results:
        st.info("Run some algorithms first to see charts.")
    else:
        results = st.session_state.results
        labels = [get_algo_short(m.config_name) for m in results]
        colors = [ALGO_COLORS.get(l, "#94A3B8") for l in labels]

        # Time comparison
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("### ⏱ Execution Time")
            times = [m.time_seconds for m in results]
            fig = go.Figure(go.Bar(
                x=labels, y=times, marker_color=colors,
                text=[f"{t:.3f}s" for t in times], textposition="outside",
                textfont_color="#F1F5F9",
            ))
            fig.update_layout(
                paper_bgcolor="#0F172A", plot_bgcolor="#1E293B",
                font_color="#F1F5F9", margin=dict(t=20,b=40),
                yaxis_title="Seconds", xaxis_tickangle=-20,
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.markdown("### 🔍 Nodes Explored")
            nodes = [m.nodes_explored for m in results]
            fig2 = go.Figure(go.Bar(
                x=labels, y=nodes, marker_color=colors,
                text=[f"{n:,}" for n in nodes], textposition="outside",
                textfont_color="#F1F5F9",
            ))
            fig2.update_layout(
                paper_bgcolor="#0F172A", plot_bgcolor="#1E293B",
                font_color="#F1F5F9", margin=dict(t=20,b=40),
                yaxis_title="Nodes", xaxis_tickangle=-20,
            )
            st.plotly_chart(fig2, use_container_width=True)

        # Quality & violations
        col_l2, col_r2 = st.columns(2)
        with col_l2:
            st.markdown("### 🌟 Solution Quality")
            quality = [m.avg_solution_quality for m in results]
            fig3 = go.Figure(go.Bar(
                x=labels, y=quality, marker_color=colors,
                text=[f"{q:.2f}" for q in quality], textposition="outside",
                textfont_color="#F1F5F9",
            ))
            fig3.update_layout(
                paper_bgcolor="#0F172A", plot_bgcolor="#1E293B",
                font_color="#F1F5F9", margin=dict(t=20,b=40),
                yaxis_title="Avg Quality Score", xaxis_tickangle=-20,
            )
            st.plotly_chart(fig3, use_container_width=True)

        with col_r2:
            st.markdown("### ⚠️ Soft Violations")
            sv = [m.soft_constraint_violations for m in results]
            fig4 = go.Figure(go.Bar(
                x=labels, y=sv, marker_color=colors,
                text=sv, textposition="outside",
                textfont_color="#F1F5F9",
            ))
            fig4.update_layout(
                paper_bgcolor="#0F172A", plot_bgcolor="#1E293B",
                font_color="#F1F5F9", margin=dict(t=20,b=40),
                yaxis_title="Violations", xaxis_tickangle=-20,
            )
            st.plotly_chart(fig4, use_container_width=True)

        # Radar chart for successful solutions
        successful = [m for m in results if m.solution_found]
        if len(successful) >= 2:
            st.markdown("### 🕸 Multi-Dimensional Comparison")
            cats = ["Speed", "Efficiency", "Quality", "Constraint Sat."]

            max_t = max(m.time_seconds for m in successful) or 1
            max_n = max(m.nodes_explored for m in successful) or 1
            max_q = max(abs(m.avg_solution_quality) for m in successful) or 1
            max_sv = max(m.soft_constraint_violations for m in successful) or 1

            radar_fig = go.Figure()
            for m in successful:
                short = get_algo_short(m.config_name)
                vals = [
                    round((1 - m.time_seconds / max_t) * 10, 2),
                    round((1 - m.nodes_explored / max_n) * 10, 2),
                    round((m.avg_solution_quality / max_q) * 10, 2) if max_q > 0 else 0,
                    round((1 - m.soft_constraint_violations / max_sv) * 10, 2),
                ]
                radar_fig.add_trace(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=cats + [cats[0]],
                    fill="toself",
                    name=short,
                    line_color=ALGO_COLORS.get(short, "#94A3B8"),
                    opacity=0.7,
                ))

            radar_fig.update_layout(
                polar=dict(bgcolor="#1E293B",
                           radialaxis=dict(visible=True, range=[0, 10],
                                           tickfont_color="#94A3B8",
                                           gridcolor="#334155"),
                           angularaxis=dict(tickfont_color="#F1F5F9",
                                            gridcolor="#334155")),
                paper_bgcolor="#0F172A",
                font_color="#F1F5F9",
                showlegend=True,
                legend_font_color="#F1F5F9",
                margin=dict(t=40, b=40),
            )
            st.plotly_chart(radar_fig, use_container_width=True)


# ══════════════════════════════════════════════
# TAB 4 – SCHEDULE VIEW
# ══════════════════════════════════════════════
with tab4:
    st.markdown("## 📅 Schedule Viewer")

    if not st.session_state.last_solution:
        st.info("No solution available yet. Run a solver first.")
    else:
        solution = st.session_state.last_solution
        rooms    = data["rooms"]
        timeslots = data["timeslots"]

        st.success(f"Showing schedule for: **{st.session_state.last_config_name}**")

        # Campus filter
        campus_filter = st.radio("Campus", ["All", "Main", "City"], horizontal=True)

        # Build day → timeslot → list[(course, room, campus)]
        schedule_map: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
        for course, (t, r) in solution.items():
            campus = rooms[r]["campus"]
            if campus_filter != "All" and campus != campus_filter:
                continue
            day, period = t.split("_", 1)
            schedule_map[day][period].append((course, r, campus))

        days = sorted(schedule_map.keys(), key=lambda d: int(d.replace("Day", "")))
        all_periods = sorted(set(
            t.split("_", 1)[1] for t in timeslots
        ))

        campus_colors = {"Main": "#1D4ED8", "City": "#065F46"}

        # Calendar grid
        for day in days:
            with st.expander(f"📆 {day}", expanded=(day == days[0])):
                cols = st.columns(len(all_periods))
                for ci, period in enumerate(all_periods):
                    with cols[ci]:
                        st.markdown(f"<div class='slot-cell-header'>{period}</div>",
                                    unsafe_allow_html=True)
                        entries = schedule_map[day].get(period, [])
                        if not entries:
                            st.markdown("<div class='slot-cell' style='color:#475569;'>—</div>",
                                        unsafe_allow_html=True)
                        for course, room, campus in entries:
                            bg = campus_colors.get(campus, "#1E293B")
                            st.markdown(
                                f"""<div class='slot-cell' style='background:{bg};border-left:3px solid {'#60A5FA' if campus=='Main' else '#34D399'}'>
                                    <b>{course[:28]}</b><br>
                                    <span style='color:#94A3B8;font-size:0.72rem'>{room} · {campus}</span>
                                </div>""",
                                unsafe_allow_html=True
                            )

        # Summary table
        st.markdown("---")
        st.markdown("### 📋 Full Schedule Table")
        rows = []
        for course, (t, r) in solution.items():
            campus = rooms[r]["campus"]
            if campus_filter != "All" and campus != campus_filter:
                continue
            day, period = t.split("_", 1)
            ci = data.get("course_info", {}).get(course, {})
            pref_t = ci.get("preferred_time", "")
            pref_c = ci.get("preferred_campus", "")
            rows.append({
                "Course": course,
                "Day": day,
                "Time": period,
                "Room": r,
                "Campus": campus,
                "Pref. Time Met": "✅" if t == pref_t else "❌",
                "Pref. Campus Met": "✅" if campus == pref_c else "❌",
            })
        if rows:
            df = pd.DataFrame(rows).sort_values(["Day", "Time"])
            st.dataframe(df, use_container_width=True, height=400)

            # Heatmap: how many exams per day per period
            st.markdown("### 🌡 Load Heatmap (Exams per Slot)")
            heat_data = defaultdict(lambda: defaultdict(int))
            for _, (t, r) in solution.items():
                day, period = t.split("_", 1)
                heat_data[day][period] += 1

            heat_df = pd.DataFrame(heat_data).fillna(0).astype(int)
            # Ensure all periods appear
            for p in all_periods:
                if p not in heat_df.index:
                    heat_df.loc[p] = 0
            heat_df = heat_df.reindex(index=sorted(heat_df.index),
                                       columns=sorted(heat_df.columns,
                                                       key=lambda d: int(d.replace("Day",""))))

            fig_heat = px.imshow(
                heat_df,
                color_continuous_scale="Blues",
                text_auto=True,
                aspect="auto",
            )
            fig_heat.update_layout(
                paper_bgcolor="#0F172A",
                plot_bgcolor="#1E293B",
                font_color="#F1F5F9",
                margin=dict(t=20, b=40),
                coloraxis_colorbar_tickfont_color="#F1F5F9",
                xaxis_title="Day",
                yaxis_title="Period",
            )
            st.plotly_chart(fig_heat, use_container_width=True)


# ══════════════════════════════════════════════
# TAB 5 – EXPLORER
# ══════════════════════════════════════════════
with tab5:
    st.markdown("## 🔍 Student & Course Explorer")

    students = data["students"]
    courses  = data["courses"]
    rooms    = data["rooms"]
    course_info = data.get("course_info", {})
    cs_map = build_course_students(students)

    explorer_mode = st.radio("Explore by", ["Student", "Course"], horizontal=True)

    if explorer_mode == "Student":
        active_students = {sid: s for sid, s in students.items() if s["courses"]}
        sid = st.selectbox("Select Student", sorted(active_students.keys()))
        if sid:
            s = students[sid]
            c1, c2, c3 = st.columns(3)
            c1.metric("Program", s["program"])
            c2.metric("Year / Sem", f"{s['year']} / {s['semester']}")
            c3.metric("Home Campus", s["home_campus"])

            st.markdown(f"**Enrolled Courses ({len(s['courses'])})**")
            for c in s["courses"]:
                ci = course_info.get(c, {})
                col_a, col_b, col_c = st.columns([3, 1, 1])
                col_a.markdown(f"📖 {c}")
                col_b.markdown(f"`{ci.get('type','')}`")
                col_c.markdown(f"Cap: {ci.get('capacity','?')}")

            if st.session_state.last_solution:
                st.markdown("---")
                st.markdown("### 📅 This Student's Exam Schedule")
                sol = st.session_state.last_solution
                rows = []
                for c in s["courses"]:
                    if c in sol:
                        t, r = sol[c]
                        day, period = t.split("_", 1)
                        rows.append({"Course": c, "Day": day,
                                     "Time": period, "Room": r,
                                     "Campus": rooms[r]["campus"]})
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

                    # Conflict check
                    conflict_graph = build_conflict_graph(courses, cs_map)
                    my_courses = s["courses"]
                    conflicts = []
                    for i, c1_ in enumerate(my_courses):
                        for c2_ in my_courses[i+1:]:
                            if c1_ in sol and c2_ in sol:
                                t1, _ = sol[c1_]
                                t2, _ = sol[c2_]
                                if t1 == t2:
                                    conflicts.append((c1_, c2_, t1))
                    if conflicts:
                        st.error(f"⚠️ {len(conflicts)} scheduling conflict(s) detected!")
                        for c1_, c2_, t in conflicts:
                            st.markdown(f"- **{c1_}** and **{c2_}** both at `{t}`")
                    else:
                        st.success("✅ No conflicts for this student.")

    else:  # Course explorer
        course_sel = st.selectbox("Select Course", sorted(courses))
        if course_sel:
            ci = course_info.get(course_sel, {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Type", ci.get("type", "—"))
            c2.metric("Capacity", ci.get("capacity", "—"))
            c3.metric("Pref. Campus", ci.get("preferred_campus", "—"))
            c4.metric("Pref. Time", ci.get("preferred_time", "—").replace("_", " ") if ci.get("preferred_time") else "—")

            enrolled = cs_map.get(course_sel, [])
            st.metric("Enrolled Students", len(enrolled))

            # Conflict courses
            conflict_graph = build_conflict_graph(courses, cs_map)
            conflicting = list(conflict_graph.get(course_sel, []))
            st.markdown(f"**Conflicts with {len(conflicting)} other courses:**")
            if conflicting:
                cols = st.columns(3)
                for i, cc in enumerate(sorted(conflicting)):
                    cols[i % 3].markdown(f"- {cc}")

            if st.session_state.last_solution and course_sel in st.session_state.last_solution:
                t, r = st.session_state.last_solution[course_sel]
                day, period = t.split("_", 1)
                campus = rooms[r]["campus"]
                st.markdown("---")
                st.markdown("### 📍 Scheduled Slot")
                sc1, sc2, sc3 = st.columns(3)
                sc1.metric("Day & Time", f"{day} · {period}")
                sc2.metric("Room", r)
                sc3.metric("Campus", campus)

                pref_t_met = t == ci.get("preferred_time")
                pref_c_met = campus == ci.get("preferred_campus")
                sc1.markdown(f"Time Pref: {'✅' if pref_t_met else '❌'}")
                sc2.markdown(f"Campus Pref: {'✅' if pref_c_met else '❌'}")