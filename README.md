# Exam Scheduler (CSP Project)

This project focuses on solving the university exam scheduling problem using Constraint Satisfaction Problem (CSP) techniques.

The aim is to generate a feasible exam timetable while considering real-world constraints such as student conflicts, room capacity, and multi-campus scheduling.

---

## Dataset

A synthetic dataset is used to simulate realistic university conditions.

It includes:
- 300 students
- 30 courses
- 4 programs (BBA, BSCS, BSAF, BSECO)
- 2 campuses

Each student is assigned 5 courses, with a mix of same-semester and cross-semester enrollments to create realistic conflicts.

Each course has a fixed capacity (30–45 students), and room capacities follow the same range.

---

## Scheduling Setup

- Each exam is 3 hours long  
- Daily time slots:
  - 08:30–11:30  
  - 11:30–14:30  
  - 14:30–17:30  

This results in 3 slots per day, requiring multi-day scheduling.

---

## Current Progress

- Dataset generator implemented  
- Structured data for CSP modeling  

---

## Next Steps

- Implement CSP solver (Backtracking)
- Add heuristics (MRV, Degree, Forward Checking)
- Run experiments and analyze performance
- Build a simple GUI for visualization

---

## Team

- Musab Bin Majid  
- Aliza Samreen Agha  
- Syeda Fatima Batool  

---

## Course

Introduction to Artificial Intelligence  
Institute of Business Administration (IBA), Karachi