from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from functools import wraps
from datetime import datetime, timedelta
import os
import random
import smtplib
from email.mime.text import MIMEText

load_dotenv()

app = Flask(__name__)

init_db()

app.secret_key = os.environ.get(
    "SECRET_KEY", "change-this-secret-before-deployment"
)
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "false").lower()
    in {"1", "true", "yes", "y"}
)

OTP_EXPIRY_MINUTES = 10


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email, otp):
    smtp_server = os.environ.get("MAIL_SERVER") or os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    smtp_port = int(os.environ.get("MAIL_PORT") or os.environ.get("SMTP_PORT") or 587)
    smtp_username = os.environ.get("MAIL_USERNAME") or os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("MAIL_PASSWORD") or os.environ.get("SMTP_PASSWORD")
    use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() in {"1", "true", "yes", "y"}
    sender_name = os.environ.get("MAIL_FROM_NAME", "InterviewMate AI")
    sender_email = os.environ.get("MAIL_FROM") or smtp_username

    if not smtp_username or not smtp_password:
        app.logger.error("OTP email is not configured; cannot send password reset email.")
        return False

    message = MIMEText(
        f"Your InterviewMate AI password reset OTP is: {otp}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.",
        "plain",
        "utf-8"
    )
    message["Subject"] = "InterviewMate AI Password Reset OTP"
    message["From"] = f"{sender_name} <{sender_email}>"
    message["To"] = email

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        if use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(sender_email, email, message.as_string())
        server.quit()
        return True
    except Exception as exc:
        print(f"[OTP ERROR] Could not send email: {exc}")
        return False


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


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Please enter your email address.")
            return redirect(url_for("forgot_password"))

        connection = get_db()
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user:
            flash("No account found with that email address.")
            connection.close()
            return redirect(url_for("forgot_password"))

        otp = generate_otp()
        expires_at = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

        connection.execute(
            "DELETE FROM password_reset_requests WHERE user_id = ?",
            (user["id"],)
        )
        connection.execute(
            "INSERT INTO password_reset_requests (user_id, otp, expires_at) VALUES (?, ?, ?)",
            (user["id"], otp, expires_at)
        )
        connection.commit()
        connection.close()

        if send_otp_email(email, otp):
            session["reset_email"] = email
            flash("An OTP has been sent to your email address.")
            return redirect(url_for("verify_otp"))

        flash("OTP could not be sent because email is not configured. Please contact support.")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        otp = request.form.get("otp", "").strip()

        if not email or not otp:
            flash("Please provide both email and OTP.")
            return redirect(url_for("verify_otp"))

        connection = get_db()
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user:
            flash("No account found with that email address.")
            connection.close()
            return redirect(url_for("verify_otp"))

        reset_request = connection.execute(
            """
            SELECT * FROM password_reset_requests
            WHERE user_id = ? AND otp = ? AND used = 0
            ORDER BY created_at DESC LIMIT 1
            """,
            (user["id"], otp)
        ).fetchone()

        if not reset_request:
            flash("Invalid or expired OTP.")
            connection.close()
            return redirect(url_for("verify_otp"))

        expires_at = datetime.strptime(reset_request["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires_at:
            flash("Your OTP has expired. Please request a new one.")
            connection.close()
            return redirect(url_for("forgot_password"))

        connection.execute(
            "UPDATE password_reset_requests SET used = 1 WHERE id = ?",
            (reset_request["id"],)
        )
        connection.commit()
        connection.close()

        session["password_reset_user_id"] = user["id"]
        session["reset_email"] = email
        flash("OTP verified successfully.")
        return redirect(url_for("reset_password"))

    return render_template("verify_otp.html", email=session.get("reset_email"))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    user_id = session.get("password_reset_user_id")
    if not user_id:
        flash("Please verify your OTP first.")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters long.")
            return redirect(url_for("reset_password"))

        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("reset_password"))

        hashed_password = generate_password_hash(password)
        connection = get_db()
        connection.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hashed_password, user_id)
        )
        connection.execute(
            "DELETE FROM password_reset_requests WHERE user_id = ?",
            (user_id,)
        )
        connection.commit()
        connection.close()

        session.pop("password_reset_user_id", None)
        session.pop("reset_email", None)
        flash("Password reset successfully. Please log in.")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


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
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )