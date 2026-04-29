import random
import json
import csv
import os

random.seed(42)

PROGRAMS = ["BBA", "BSCS", "BSAF", "BSECO"]
CAMPUSES = ["Main", "City"]

COURSE_PROGRAM_MAP = {
    "Introduction to Programming": ["BSCS"],
    "Data Structures": ["BSCS"],
    "Human Computer Interaction": ["BSCS"],
    "Reinforcement Learning": ["BSCS"],
    "Machine Learning": ["BSCS"],
    "Data Warehousing": ["BSCS"],

    "Business Communication": ["BBA", "BSAF"],
    "Introduction to Business Finance": ["BBA", "BSAF"],
    "Financial Institutions and Markets": ["BSAF"],
    "Principles of Marketing": ["BBA"],
    "Human Resource Management": ["BBA"],
    "Business Intelligence": ["BBA"],

    "Microeconomics": ["BSECO", "BBA"],
    "Principles of Microeconomics": ["BSECO", "BBA"],
    "Managerial Economics": ["BBA"],
    "Applied Econometrics": ["BSECO"],
    "Environmental Economics": ["BSECO"],

    "Discrete Mathematics": ["BSCS", "BSECO"],
    "Partial Differential Equations": ["BSECO"],

    "Introduction to Business Ethics": ["ALL"],
    "History of Ideas": ["ALL"],
    "Arabic Language": ["ALL"],
    "French Language": ["ALL"],
    "Introduction to Trade Marketing": ["ALL"],
    "Accounting for Shariah Compliance": ["ALL"],
    "Statistical Inference": ["ALL"],
    "Advanced Business Research": ["ALL"],

    "International Financial Management": ["BSAF"],
    "Regulation and Financial Market": ["BSAF"],
    "Business Finance": ["BBA", "BSAF"]
}

COURSES = list(COURSE_PROGRAM_MAP.keys())


def generate_dataset(difficulty):

    if difficulty == "easy":
        num_students = 250    # was 120
        num_days = 3          # was 2
        rooms_per_campus = 12 # was 10
    elif difficulty == "medium":
        num_students = 350    # was 200
        num_days = 4          # was 3
        rooms_per_campus = 14 # was 10
    else:  # hard
        num_students = 400    # was 300
        num_days = 5          # was 4
        rooms_per_campus = 16 # was 10

    rooms = {}
    for campus in CAMPUSES:
        for i in range(1, rooms_per_campus + 1):
            rooms[f"{campus}_R{i}"] = {
                "capacity": random.randint(30, 45),
                "campus": campus
            }

    daily_slots = [
        "08:30-11:30",
        "11:30-14:30",
        "14:30-17:30"
    ]

    timeslots = []
    for d in range(1, num_days + 1):
        for t in daily_slots:
            timeslots.append(f"Day{d}_{t}")

    course_info = {}
    course_capacity = {}
    course_students = {}

    for course, programs in COURSE_PROGRAM_MAP.items():
        cap = random.randint(30, 45)

        course_capacity[course] = cap
        course_students[course] = []

        course_info[course] = {
            "programs": programs,
            "semester": random.randint(1, 8),
            "capacity": cap,
            "type": "core" if "ALL" not in programs else "elective",
            "preferred_campus": random.choice(CAMPUSES),
            "preferred_time": random.choice(timeslots)
        }

    students = {}

    per_program = num_students // len(PROGRAMS)
    student_id = 1

    for program in PROGRAMS:
        for _ in range(per_program):
            sid = f"S{student_id}"
            semester = random.randint(1, 8)

            students[sid] = {
                "program": program,
                "year": random.randint(1, 4),
                "semester": semester,
                "home_campus": random.choice(CAMPUSES),
                "courses": []
            }

            student_id += 1

    student_ids = list(students.keys())

    for sid in student_ids:

        student = students[sid]
        program = student["program"]
        semester = student["semester"]

        same_sem = []
        other_courses = []

        for c, info in course_info.items():
            if "ALL" in info["programs"]:
                other_courses.append(c)
            elif program in info["programs"]:
                if info["semester"] == semester:
                    same_sem.append(c)
                else:
                    other_courses.append(c)

        selected = []

        # 3 same semester
        same_choices = random.sample(same_sem, min(3, len(same_sem)))
        for c in same_choices:
            if len(course_students[c]) < course_capacity[c]:
                selected.append(c)
                course_students[c].append(sid)

        # 2 cross-sem / electives
        random.shuffle(other_courses)
        for c in other_courses:
            if len(selected) == 5:
                break
            if len(course_students[c]) < course_capacity[c]:
                selected.append(c)
                course_students[c].append(sid)

        student["courses"] = selected

    return {
        "students": students,
        "courses": COURSES,
        "rooms": rooms,
        "timeslots": timeslots,
        "campuses": CAMPUSES,
        "course_info": course_info
    }

def save_all(data, name):

    os.makedirs("data", exist_ok=True)

    with open(f"data/{name}.json", "w") as f:
        json.dump(data, f, indent=4)

    with open(f"data/{name}_students.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id", "program", "year", "semester", "campus", "courses"])

        for sid, info in data["students"].items():
            writer.writerow([
                sid,
                info["program"],
                info["year"],
                info["semester"],
                info["home_campus"],
                "|".join(info["courses"])
            ])

    with open(f"data/{name}_rooms.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["room", "capacity", "campus"])

        for r, info in data["rooms"].items():
            writer.writerow([r, info["capacity"], info["campus"]])

    with open(f"data/{name}_timeslots.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timeslot"])
        for t in data["timeslots"]:
            writer.writerow([t])

if __name__ == "__main__":
    easy   = generate_dataset("easy")
    medium = generate_dataset("medium")
    hard   = generate_dataset("hard")

    save_all(easy,   "easy")
    save_all(medium, "medium")
    save_all(hard,   "hard")

    print(f"Success")
    