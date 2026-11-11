from flask import (
    Flask, Response, jsonify, render_template, request,
    redirect, url_for, session, flash
)

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from functools import lru_cache, wraps
from datetime import datetime, timedelta
import json
import os
import random
import smtplib
import urllib.error
import urllib.request
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


@lru_cache(maxsize=90)
def synthesize_question_audio(question):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    payload = json.dumps({
        "model": "gpt-4o-mini-tts",
        "voice": "marin",
        "input": question,
        "instructions": (
            "Speak clearly and naturally as a friendly professional interviewer "
            "asking a candidate this interview question."
        ),
        "response_format": "mp3"
    }).encode("utf-8")
    api_request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urllib.request.urlopen(api_request, timeout=30) as response:
        return response.read()


QUESTIONS = {
    "Python Developer": {
        "Beginner": [
            "What are some key features of Python?",
            "How are lists and tuples different, and when would you use each?",
            "What is the difference between a mutable and an immutable object?",
            "How do you handle exceptions in Python?",
            "What is a Python dictionary, and how do you look up a value?",
            "What is the purpose of a virtual environment?",
            "How does a for loop differ from a while loop?",
            "What is the difference between a module and a package?",
            "How would you read a file safely in Python?",
            "How would you sort a list of dictionaries by one of their values?"
        ],
        "Intermediate": [
            "What are decorators, and where have you used one?",
            "Explain generators and how they differ from returning a list.",
            "How does Python manage memory and garbage collection?",
            "What is the difference between threading and multiprocessing in Python?",
            "How do context managers work, and how would you create one?",
            "What are *args and **kwargs used for?",
            "How would you write and test a reusable API client?",
            "What is the Global Interpreter Lock, and when does it matter?",
            "How do you structure a medium-sized Python application?",
            "How would you design a cache with expiration and invalidation?"
        ],
        "Advanced": [
            "How would you profile and optimize a Python service with high latency?",
            "Describe a robust strategy for managing concurrent tasks in Python.",
            "How would you design a plugin architecture using Python?",
            "What trade-offs would you consider when choosing between async I/O and threads?",
            "How do Python descriptors and the method resolution order work?",
            "How would you make a data-processing pipeline memory efficient?",
            "How do you design backward-compatible Python library APIs?",
            "What are common causes of memory leaks in long-running Python processes?",
            "How would you investigate and resolve contention in a high-throughput service?",
            "How would you ensure a Python service shuts down gracefully while cleaning up resources?"
        ]
    },
    "Web Developer": {
        "Beginner": [
            "What is semantic HTML, and why is it useful?",
            "How do the CSS box model and box-sizing property work?",
            "What is the difference between a class and an ID in CSS?",
            "What happens when a browser loads a web page?",
            "What is the difference between GET and POST requests?",
            "How do you make a web page responsive?",
            "What is the purpose of HTML forms and their labels?",
            "How do CSS Flexbox and Grid help with layouts?",
            "What is an API, and how does a web page use one?",
            "How do alt text and descriptive link labels help people use a website?"
        ],
        "Intermediate": [
            "How do you manage client-side state in a complex web application?",
            "What is the difference between authentication and authorization?",
            "How would you improve the performance of a slow-loading page?",
            "How do promises and async/await help manage asynchronous JavaScript?",
            "What are common causes of cross-browser layout differences?",
            "How would you design and validate a REST API endpoint?",
            "How do you make interactive components accessible?",
            "What is the purpose of content security policy headers?",
            "How do you test a web interface across different screen sizes?",
            "How would you reduce unnecessary re-renders in a component-based interface?"
        ],
        "Advanced": [
            "How would you diagnose a production web performance regression?",
            "How would you design a frontend architecture for a large team?",
            "What trade-offs do server-side rendering and client-side rendering introduce?",
            "How would you plan a safe migration from a legacy frontend?",
            "How do caching strategies affect consistency and freshness in web applications?",
            "How would you prevent a slow third-party script from blocking the user experience?",
            "How would you design resilient frontend behavior for unreliable networks?",
            "What metrics would you use to assess real-user web performance?",
            "How would you approach accessibility in a large existing product?",
            "How would you safely roll out a major frontend change to users?"
        ]
    },
    "Java Developer": {
        "Beginner": [
            "What is the difference between the JDK, JRE, and JVM?",
            "How do classes and objects relate in Java?",
            "What is inheritance, and when is it useful?",
            "How do primitive types differ from reference types?",
            "What is the difference between an interface and a class?",
            "How do you handle exceptions in Java?",
            "What are the main access modifiers in Java?",
            "How does an ArrayList differ from an array?",
            "What is method overloading?",
            "How do String, StringBuilder, and StringBuffer differ?"
        ],
        "Intermediate": [
            "How do equals() and hashCode() work together?",
            "When would you use a Java Stream instead of a loop?",
            "How does the Java garbage collector affect application performance?",
            "What is dependency injection, and what problem does it solve?",
            "How do checked and unchecked exceptions differ?",
            "How would you make a Java class immutable?",
            "What are the benefits and risks of using CompletableFuture?",
            "How do HashMap and ConcurrentHashMap differ?",
            "How do you organize tests for a Spring service?",
            "When is Optional useful, and when should you avoid using it?"
        ],
        "Advanced": [
            "How would you investigate long garbage-collection pauses in production?",
            "How would you design a high-throughput Java service?",
            "What trade-offs do different JVM garbage collectors offer?",
            "How do Java memory-model guarantees affect concurrent code?",
            "How would you evolve a Java API without breaking existing clients?",
            "How would you diagnose thread-pool saturation in a production service?",
            "What design considerations matter when building a distributed Java system?",
            "How would you reduce allocation pressure in a latency-sensitive application?",
            "How would you structure observability for a large Java platform?",
            "How would you plan a safe Java runtime upgrade across multiple services?"
        ]
    }
}

DIFFICULTIES = ("Beginner", "Intermediate", "Advanced")
QUESTIONS_PER_INTERVIEW = 5


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
        difficulties=DIFFICULTIES,
        history=history
    )


@app.route("/interview", methods=["GET", "POST"])
@login_required
def interview():
    if request.method == "POST":
        role = request.form.get("role")
        difficulty = request.form.get("difficulty")

        if role not in QUESTIONS:
            flash("Please select a valid job role.")
            return redirect(url_for("dashboard"))

        if difficulty not in DIFFICULTIES:
            flash("Please select a valid difficulty level.")
            return redirect(url_for("dashboard"))

        connection = get_db()
        completed_questions = {
            row["question"] for row in connection.execute(
                """SELECT question FROM interviews
                   WHERE user_id = ? AND role = ? AND difficulty = ?""",
                (session["user_id"], role, difficulty)
            ).fetchall()
        }
        connection.close()

        question_pool = QUESTIONS[role][difficulty]
        unseen_questions = [
            question for question in question_pool
            if question not in completed_questions
        ]
        question_count = min(QUESTIONS_PER_INTERVIEW, len(question_pool))
        if len(unseen_questions) >= question_count:
            interview_questions = random.sample(unseen_questions, question_count)
        else:
            previously_seen = [
                question for question in question_pool
                if question in completed_questions
            ]
            interview_questions = unseen_questions + random.sample(
                previously_seen, question_count - len(unseen_questions)
            )
            random.shuffle(interview_questions)

        session["role"] = role
        session["difficulty"] = difficulty
        session["interview_questions"] = interview_questions
        session["question_index"] = 0
        session["answers"] = []

        return redirect(url_for("interview"))

    role = session.get("role")
    difficulty = session.get("difficulty")
    questions = session.get("interview_questions", [])

    if role not in QUESTIONS or difficulty not in DIFFICULTIES or not questions:
        return redirect(url_for("dashboard"))

    index = session.get("question_index", 0)

    if index >= len(questions):
        return redirect(url_for("result"))

    return render_template(
        "interview.html",
        role=role,
        difficulty=difficulty,
        question=questions[index],
        number=index + 1,
        total=len(questions),
        progress=round(index / len(questions) * 100),
        voice_enabled=bool(os.environ.get("OPENAI_API_KEY"))
    )


@app.route("/api/question-audio", methods=["POST"])
def question_audio():
    if "user_id" not in session:
        return jsonify(error="Please log in to hear interview questions."), 401

    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify(error="Invalid request."), 400

    if not os.environ.get("OPENAI_API_KEY"):
        return jsonify(error="Voice is not configured. Add OPENAI_API_KEY to the server environment."), 503

    role = session.get("role")
    difficulty = session.get("difficulty")
    questions = session.get("interview_questions", [])
    index = session.get("question_index", 0)
    if (
        role not in QUESTIONS or difficulty not in DIFFICULTIES
        or not isinstance(index, int) or index < 0
        or index >= len(questions)
    ):
        return jsonify(error="There is no active interview question to read."), 409

    question = questions[index]
    if question not in QUESTIONS[role][difficulty]:
        return jsonify(error="The current interview question is invalid."), 409

    try:
        audio = synthesize_question_audio(question)
    except urllib.error.HTTPError as error:
        app.logger.error("OpenAI text-to-speech returned HTTP %s.", error.code)
        error.close()
        return jsonify(error="Voice generation failed. Please try again later."), 502
    except (urllib.error.URLError, TimeoutError) as error:
        app.logger.error("Could not reach OpenAI text-to-speech: %s", error)
        return jsonify(error="Voice service could not be reached. Please try again."), 502

    return Response(
        audio,
        mimetype="audio/mpeg",
        headers={"Cache-Control": "private, no-store"}
    )


@app.route("/submit-answer", methods=["POST"])
@login_required
def submit_answer():
    role = session.get("role")
    difficulty = session.get("difficulty")
    index = session.get("question_index", 0)
    questions = session.get("interview_questions", [])

    if (
        role not in QUESTIONS or difficulty not in DIFFICULTIES
        or not questions or index >= len(questions)
    ):
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
    difficulty = session.get("difficulty")
    answers = session.get("answers", [])
    questions = session.get("interview_questions", [])

    if (
        role not in QUESTIONS or difficulty not in DIFFICULTIES
        or not questions or len(answers) != len(questions)
    ):
        return redirect(url_for("dashboard"))

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
               (user_id, role, difficulty, question, answer, score, feedback)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session["user_id"], role, difficulty, question,
                answer, score, feedback
            )
        )

    connection.commit()
    connection.close()

    session.pop("role", None)
    session.pop("difficulty", None)
    session.pop("interview_questions", None)
    session.pop("question_index", None)
    session.pop("answers", None)

    return render_template(
        "result.html",
        score=overall_score,
        role=role,
        difficulty=difficulty,
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