FIRST_PRIMARY_GRADE = "grade_1_primary"
SECOND_PRIMARY_GRADE = "grade_2_primary"
THIRD_PRIMARY_GRADE = "grade_3_primary"
FOURTH_PRIMARY_GRADE = "grade_4_primary"
FIFTH_PRIMARY_GRADE = "grade_5_primary"
SIXTH_PRIMARY_GRADE = "grade_6_primary"
FIRST_PREPARATORY_GRADE = "grade_1_preparatory"
SECOND_PREPARATORY_GRADE = "grade_2_preparatory"
THIRD_PREPARATORY_GRADE = "grade_3_preparatory"
FIRST_SECONDARY_GRADE = "grade_1_secondary"
SECOND_SECONDARY_GRADE = "grade_2_secondary"
THIRD_SECONDARY_GRADE = "grade_3_secondary"

GENERAL_BRANCH = "general"
SCIENCE_BRANCH = "science"
LITERARY_BRANCH = "literary"

PHYSICS_AND_CHEMISTRY = "Physics & Chemistry"

FIRST_SECONDARY_SUBJECTS = (
    "Mathematics",
    "Biology",
    PHYSICS_AND_CHEMISTRY,
    "Arabic Language",
    "Foreign Language",
    "French Language",
    "History",
    "Geography",
    "National Education",
)

SECONDARY_BRANCH_SUBJECTS = {
    SCIENCE_BRANCH: (
        "Mathematics",
        "Biology",
        "Physics",
        "Chemistry",
        "Arabic Language",
        "Foreign Language",
        "French Language",
    ),
    LITERARY_BRANCH: (
        "Arabic Language",
        "Foreign Language",
        "French Language",
        "Philosophy & Sociology",
        "History",
        "Geography",
        "National Education",
    ),
}

PREPARATORY_SUBJECT_REPLACEMENTS = {
    "Physics": PHYSICS_AND_CHEMISTRY,
    "Chemistry": PHYSICS_AND_CHEMISTRY,
}

GENERAL_ONLY_GRADES = {
    FIRST_PRIMARY_GRADE,
    SECOND_PRIMARY_GRADE,
    THIRD_PRIMARY_GRADE,
    FOURTH_PRIMARY_GRADE,
    FIFTH_PRIMARY_GRADE,
    SIXTH_PRIMARY_GRADE,
    FIRST_PREPARATORY_GRADE,
    SECOND_PREPARATORY_GRADE,
    THIRD_PREPARATORY_GRADE,
    FIRST_SECONDARY_GRADE,
}

BRANCHED_SECONDARY_GRADES = {
    SECOND_SECONDARY_GRADE,
    THIRD_SECONDARY_GRADE,
}

TEACHER_SPECIALIZATION_CHOICES = tuple(
    (subject, subject)
    for subject in dict.fromkeys(
        FIRST_SECONDARY_SUBJECTS
        + SECONDARY_BRANCH_SUBJECTS[SCIENCE_BRANCH]
        + SECONDARY_BRANCH_SUBJECTS[LITERARY_BRANCH]
    )
)

STUDENT_LOGIN_SUBJECTS = {
    "الصف الأول الثانوي": {
        "general": list(FIRST_SECONDARY_SUBJECTS),
    },
    "الصف الثاني الثانوي": {
        "science": list(SECONDARY_BRANCH_SUBJECTS[SCIENCE_BRANCH]),
        "literary": list(SECONDARY_BRANCH_SUBJECTS[LITERARY_BRANCH]),
    },
    "الصف الثالث الثانوي": {
        "science": list(SECONDARY_BRANCH_SUBJECTS[SCIENCE_BRANCH]),
        "literary": list(SECONDARY_BRANCH_SUBJECTS[LITERARY_BRANCH]),
    },
}


def is_general_only_grade(grade_level):
    return grade_level in GENERAL_ONLY_GRADES



def requires_secondary_branch(grade_level):
    return grade_level in BRANCHED_SECONDARY_GRADES



def branch_validation_error(grade_level, branch):
    if not grade_level or not branch:
        return None

    if requires_secondary_branch(grade_level) and branch == GENERAL_BRANCH:
        return "Second and third secondary grades require either the Science or Literary branch."

    if is_general_only_grade(grade_level) and branch != GENERAL_BRANCH:
        return "Only second and third secondary grades can use the Science or Literary branch."

    return None
