from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)

from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from functools import wraps
import os

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY", "change-this-secret-before-deployment"
)

QUESTIONS = {
    "Python Developer": [
        "What is Python and why is it popular?",
        "What is the difference between a list and a tuple?",
        "Explain object-oriented programming."
    ],
    "Web Developer": [
        "What is HTML?",
        "What is the difference between CSS and JavaScript?",
        "What is an API?"
    ],
    "Java Developer": [
        "What is Java?",
        "Explain inheritance in Java.",
        "What is the difference between JDK and JRE?"
    ]
}


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 8:
            flash("Enter your details and a password of at least 8 characters.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        connection = get_db()

        try:
            connection.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )
            connection.commit()
            flash("Registration successful! Please log in.")
            return redirect(url_for("login"))

        except Exception:
            flash("This email may already be registered.")

        finally:
            connection.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db()
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        connection.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    connection = get_db()

    history = connection.execute(
        """SELECT * FROM interviews
           WHERE user_id = ?
           ORDER BY id DESC LIMIT 5""",
        (session["user_id"],)
    ).fetchall()

    connection.close()

    return render_template(
        "dashboard.html",
        name=session["name"],
        roles=QUESTIONS.keys(),
        history=history
    )


@app.route("/interview", methods=["GET", "POST"])
@login_required
def interview():
    if request.method == "POST":
        role = request.form.get("role")

        if role not in QUESTIONS:
            flash("Please select a valid job role.")
            return redirect(url_for("dashboard"))

        session["role"] = role
        session["question_index"] = 0
        session["answers"] = []

        return redirect(url_for("interview"))

    role = session.get("role")

    if not role:
        return redirect(url_for("dashboard"))

    index = session.get("question_index", 0)
    questions = QUESTIONS[role]

    if index >= len(questions):
        return redirect(url_for("result"))

    return render_template(
        "interview.html",
        role=role,
        question=questions[index],
        number=index + 1,
        total=len(questions)
    )


@app.route("/submit-answer", methods=["POST"])
@login_required
def submit_answer():
    role = session.get("role")
    index = session.get("question_index", 0)
    questions = QUESTIONS.get(role)

    if not questions or index >= len(questions):
        return redirect(url_for("dashboard"))

    answer = request.form.get("answer", "").strip()

    if not answer:
        flash("Please enter your answer.")
        return redirect(url_for("interview"))

    session["answers"] = session.get("answers", []) + [answer]
    session["question_index"] = index + 1

    return redirect(url_for("interview"))


@app.route("/result")
@login_required
def result():
    role = session.get("role")
    answers = session.get("answers", [])

    if not role or len(answers) != len(QUESTIONS.get(role, [])):
        return redirect(url_for("dashboard"))

    questions = QUESTIONS[role]

    # Starter evaluation: answer completeness, not AI evaluation.
    scores = []
    feedback_list = []

    for answer in answers:
        word_count = len(answer.split())

        if word_count >= 40:
            score = 90
            feedback = "Good detail. Try adding a practical example."
        elif word_count >= 20:
            score = 75
            feedback = "Good start. Explain your answer in more detail."
        else:
            score = 50
            feedback = "Try giving a longer and more complete answer."

        scores.append(score)
        feedback_list.append(feedback)

    overall_score = round(sum(scores) / len(scores))

    connection = get_db()

    for question, answer, score, feedback in zip(
        questions, answers, scores, feedback_list
    ):
        connection.execute(
            """INSERT INTO interviews
               (user_id, role, question, answer, score, feedback)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session["user_id"], role, question,
                answer, score, feedback
            )
        )

    connection.commit()
    connection.close()

    session.pop("role", None)
    session.pop("question_index", None)
    session.pop("answers", None)

    return render_template(
        "result.html",
        score=overall_score,
        feedback_list=feedback_list,
        answers=answers,
        questions=questions
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)