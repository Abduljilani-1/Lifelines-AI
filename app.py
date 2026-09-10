from flask import Flask, render_template, request, redirect, url_for, session
import pymysql
import random
import time
import os
from datetime import datetime, timedelta, time as dt_time

from flask_mail import Mail, Message
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
# LOAD ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "lifelens_ai_secret"
)


# =========================================================
# MAIL CONFIGURATION
# =========================================================

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

mail = Mail(app)


# =========================================================
# DATABASE
# =========================================================

def get_db_connection():

    return pymysql.connect(
        host="localhost",
        user="root",
        password="Abdul@123",
        database="lifelens_ai",
        cursorclass=pymysql.cursors.DictCursor
    )


# =========================================================
# HELPER - CONVERT MYSQL TIME TO PYTHON TIME
# =========================================================
# MySQL TIME values can come through PyMySQL as timedelta.
# This converts them into datetime.time so .strftime()
# works correctly inside sleep.html.
# =========================================================

def convert_mysql_time(value):

    if value is None:
        return None

    # MySQL TIME can come as timedelta
    if isinstance(value, timedelta):

        total_seconds = int(value.total_seconds())

        # Keep time inside 24 hours
        total_seconds = total_seconds % (24 * 60 * 60)

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return dt_time(
            hour=hours,
            minute=minutes,
            second=seconds
        )

    # If already datetime.time
    if isinstance(value, dt_time):
        return value

    # If datetime
    if isinstance(value, datetime):
        return value.time()

    # If string
    if isinstance(value, str):

        for fmt in ("%H:%M:%S", "%H:%M"):

            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                pass

    return value


# =========================================================
# HELPER - CALCULATE SLEEP DURATION
# =========================================================

def calculate_sleep_duration(bedtime, wake_time):

    bedtime = convert_mysql_time(bedtime)
    wake_time = convert_mysql_time(wake_time)

    if bedtime is None or wake_time is None:
        return "0h 0m"

    today = datetime.today().date()

    bedtime_dt = datetime.combine(today, bedtime)
    wake_dt = datetime.combine(today, wake_time)

    # If wake time is earlier than bedtime,
    # it means the person slept overnight.
    if wake_dt <= bedtime_dt:
        wake_dt += timedelta(days=1)

    duration = wake_dt - bedtime_dt

    total_minutes = int(duration.total_seconds() // 60)

    hours = total_minutes // 60
    minutes = total_minutes % 60

    return f"{hours}h {minutes}m"


# =========================================================
# HELPER - PREPARE SLEEP RECORDS
# =========================================================

def prepare_sleep_records(records):

    prepared_records = []

    for record in records:

        record["bedtime"] = convert_mysql_time(
            record.get("bedtime")
        )

        record["wake_time"] = convert_mysql_time(
            record.get("wake_time")
        )

        record["sleep_duration"] = calculate_sleep_duration(
            record.get("bedtime"),
            record.get("wake_time")
        )

        prepared_records.append(record)

    return prepared_records


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template("home.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if not name or not email or not password:

            return render_template(
                "register.html",
                error="Please fill in all required fields."
            )

        if password != confirm_password:

            return render_template(
                "register.html",
                error="Passwords do not match."
            )

        if len(password) < 8:

            return render_template(
                "register.html",
                error="Password must contain at least 8 characters."
            )

        connection = None
        cursor = None

        try:

            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            existing_user = cursor.fetchone()

            if existing_user:

                return render_template(
                    "register.html",
                    error="This email is already registered."
                )

            hashed_password = generate_password_hash(
                password
            )

            cursor.execute(
                """
                INSERT INTO users
                (
                    name,
                    email,
                    password
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    name,
                    email,
                    hashed_password
                )
            )

            connection.commit()

            return render_template(
                "login.html",
                success="Registration successful! Please login."
            )

        except pymysql.err.IntegrityError:

            if connection:
                connection.rollback()

            return render_template(
                "register.html",
                error="This email is already registered."
            )

        except Exception as e:

            print(
                "REGISTER ERROR:",
                e
            )

            if connection:
                connection.rollback()

            return render_template(
                "register.html",
                error="Something went wrong. Please try again."
            )

        finally:

            if cursor:
                cursor.close()

            if connection:
                connection.close()

    return render_template("register.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not email or not password:

            return render_template(
                "login.html",
                error="Please enter your email and password."
            )

        connection = None
        cursor = None

        try:

            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            user = cursor.fetchone()

            if user:

                stored_password = user["password"]

                password_correct = False

                try:

                    password_correct = check_password_hash(
                        stored_password,
                        password
                    )

                except Exception:

                    password_correct = False

                # SUPPORT OLD PLAIN TEXT PASSWORDS

                if (
                    not password_correct
                    and stored_password == password
                ):

                    password_correct = True

                    new_hash = generate_password_hash(
                        password
                    )

                    cursor.execute(
                        """
                        UPDATE users
                        SET password = %s
                        WHERE id = %s
                        """,
                        (
                            new_hash,
                            user["id"]
                        )
                    )

                    connection.commit()

                if password_correct:

                    session["user_id"] = user["id"]
                    session["user_name"] = user["name"]

                    return redirect(
                        url_for("dashboard")
                    )

            return render_template(
                "login.html",
                error="Incorrect email or password."
            )

        except Exception as e:

            print(
                "LOGIN ERROR:",
                e
            )

            return render_template(
                "login.html",
                error="Something went wrong. Please try again."
            )

        finally:

            if cursor:
                cursor.close()

            if connection:
                connection.close()

    return render_template("login.html")


# =========================================================
# FORGOT PASSWORD
# =========================================================

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        if not email:

            return render_template(
                "forgot_password.html",
                error="Please enter your registered email."
            )

        connection = None
        cursor = None

        try:

            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            user = cursor.fetchone()

            if not user:

                return render_template(
                    "forgot_password.html",
                    error="This email is not registered."
                )

            otp = str(
                random.randint(
                    100000,
                    999999
                )
            )

            session["reset_email"] = email
            session["reset_otp"] = otp
            session["otp_created"] = time.time()
            session["otp_verified"] = False

            message = Message(
                subject="LifeLens AI - Password Reset OTP",
                sender=app.config["MAIL_USERNAME"],
                recipients=[email]
            )

            message.body = f"""
Hello {user["name"]},

Your LifeLens AI password reset OTP is:

{otp}

This OTP is valid for 1 minute.

Regards,
LifeLens AI
"""

            mail.send(message)

            print(
                "OTP sent successfully to:",
                email
            )

            return redirect(
                url_for("verify_otp")
            )

        except Exception as e:

            print(
                "FORGOT PASSWORD ERROR:",
                e
            )

            return render_template(
                "forgot_password.html",
                error="Unable to send OTP. Please try again."
            )

        finally:

            if cursor:
                cursor.close()

            if connection:
                connection.close()

    return render_template("forgot_password.html")


# =========================================================
# VERIFY OTP
# =========================================================

@app.route(
    "/verify-otp",
    methods=["GET", "POST"]
)
def verify_otp():

    if "reset_email" not in session:

        return redirect(
            url_for("forgot_password")
        )

    if request.method == "POST":

        entered_otp = request.form.get(
            "otp",
            ""
        ).strip()

        correct_otp = session.get(
            "reset_otp"
        )

        created_time = session.get(
            "otp_created"
        )

        if not correct_otp or not created_time:

            return render_template(
                "verify_otp.html",
                error="OTP session expired."
            )

        if time.time() - created_time > 60:

            session.pop(
                "reset_otp",
                None
            )

            session.pop(
                "otp_created",
                None
            )

            session["otp_verified"] = False

            return render_template(
                "verify_otp.html",
                error="OTP expired. Please request a new OTP."
            )

        if entered_otp == correct_otp:

            session["otp_verified"] = True

            return redirect(
                url_for("reset_password")
            )

        return render_template(
            "verify_otp.html",
            error="Invalid OTP."
        )

    return render_template("verify_otp.html")


# =========================================================
# RESEND OTP
# =========================================================

@app.route("/resend-otp")
def resend_otp():

    email = session.get(
        "reset_email"
    )

    if not email:

        return redirect(
            url_for("forgot_password")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = %s
            """,
            (email,)
        )

        user = cursor.fetchone()

        if not user:

            return redirect(
                url_for("forgot_password")
            )

        otp = str(
            random.randint(
                100000,
                999999
            )
        )

        session["reset_otp"] = otp
        session["otp_created"] = time.time()
        session["otp_verified"] = False

        message = Message(
            subject="LifeLens AI - New Password Reset OTP",
            sender=app.config["MAIL_USERNAME"],
            recipients=[email]
        )

        message.body = f"""
Hello {user["name"]},

Your new LifeLens AI password reset OTP is:

{otp}

This OTP is valid for 1 minute.

Regards,
LifeLens AI
"""

        mail.send(message)

        print(
            "New OTP sent successfully to:",
            email
        )

        return redirect(
            url_for("verify_otp")
        )

    except Exception as e:

        print(
            "RESEND OTP ERROR:",
            e
        )

        return render_template(
            "verify_otp.html",
            error="Unable to resend OTP."
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# =========================================================
# RESET PASSWORD
# =========================================================

@app.route(
    "/reset-password",
    methods=["GET", "POST"]
)
def reset_password():

    if "reset_email" not in session:

        return redirect(
            url_for("forgot_password")
        )

    if not session.get("otp_verified"):

        return redirect(
            url_for("verify_otp")
        )

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if password != confirm_password:

            return render_template(
                "reset_password.html",
                error="Passwords do not match."
            )

        if len(password) < 8:

            return render_template(
                "reset_password.html",
                error="Password must contain at least 8 characters."
            )

        email = session["reset_email"]

        connection = None
        cursor = None

        try:

            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT password
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            user = cursor.fetchone()

            if not user:

                return redirect(
                    url_for("forgot_password")
                )

            old_password = user["password"]

            try:

                old_password_match = check_password_hash(
                    old_password,
                    password
                )

            except Exception:

                old_password_match = (
                    old_password == password
                )

            if old_password_match:

                return render_template(
                    "reset_password.html",
                    error="Please choose a new password."
                )

            hashed_password = generate_password_hash(
                password
            )

            cursor.execute(
                """
                UPDATE users
                SET password = %s
                WHERE email = %s
                """,
                (
                    hashed_password,
                    email
                )
            )

            connection.commit()

            session.clear()

            return render_template(
                "login.html",
                success="Password changed successfully!"
            )

        except Exception as e:

            print(
                "RESET PASSWORD ERROR:",
                e
            )

            if connection:
                connection.rollback()

            return render_template(
                "reset_password.html",
                error="Unable to reset password."
            )

        finally:

            if cursor:
                cursor.close()

            if connection:
                connection.close()

    return render_template("reset_password.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    return render_template(
        "dashboard.html",
        name=session.get("user_name")
    )


# =========================================================
# MONEY
# =========================================================

@app.route("/money")
def money():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        user_id = session["user_id"]

        # =====================================================
        # ALL TRANSACTIONS
        # =====================================================

        cursor.execute(
            """
            SELECT *
            FROM money_transactions
            WHERE user_id = %s
            ORDER BY transaction_date DESC, id DESC
            """,
            (user_id,)
        )

        transactions = cursor.fetchall()

        # =====================================================
        # TOTAL INCOME
        # =====================================================

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total_income
            FROM money_transactions
            WHERE user_id = %s
            AND transaction_type = 'Income'
            """,
            (user_id,)
        )

        total_income = cursor.fetchone()["total_income"] or 0

        # =====================================================
        # TOTAL EXPENSE
        # =====================================================

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total_expense
            FROM money_transactions
            WHERE user_id = %s
            AND transaction_type = 'Expense'
            """,
            (user_id,)
        )

        total_expense = cursor.fetchone()["total_expense"] or 0

        # =====================================================
        # CURRENT BALANCE
        # =====================================================

        balance = total_income - total_expense

        # =====================================================
        # MONTHLY INCOME
        # =====================================================

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS monthly_income
            FROM money_transactions
            WHERE user_id = %s
            AND transaction_type = 'Income'
            AND YEAR(transaction_date) = YEAR(CURDATE())
            AND MONTH(transaction_date) = MONTH(CURDATE())
            """,
            (user_id,)
        )

        monthly_income = cursor.fetchone()["monthly_income"] or 0

        # =====================================================
        # MONTHLY EXPENSE
        # =====================================================

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS monthly_expense
            FROM money_transactions
            WHERE user_id = %s
            AND transaction_type = 'Expense'
            AND YEAR(transaction_date) = YEAR(CURDATE())
            AND MONTH(transaction_date) = MONTH(CURDATE())
            """,
            (user_id,)
        )

        monthly_expense = cursor.fetchone()["monthly_expense"] or 0

        # =====================================================
        # MONTHLY BALANCE
        # =====================================================

        monthly_balance = monthly_income - monthly_expense

        # =====================================================
        # SPENDING BY CATEGORY
        # =====================================================

        cursor.execute(
            """
            SELECT
                category,
                SUM(amount) AS total
            FROM money_transactions
            WHERE user_id = %s
            AND transaction_type = 'Expense'
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id,)
        )

        category_expenses = cursor.fetchall()

        # =====================================================
        # SEND DATA TO HTML
        # =====================================================

        return render_template(
            "money.html",

            transactions=transactions,

            total_income=total_income,

            total_expense=total_expense,

            balance=balance,

            monthly_income=monthly_income,

            monthly_expense=monthly_expense,

            monthly_balance=monthly_balance,

            category_expenses=category_expenses
        )

    except Exception as e:

        print(
            "MONEY ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

        return render_template(
            "money.html",

            transactions=[],

            total_income=0,

            total_expense=0,

            balance=0,

            monthly_income=0,

            monthly_expense=0,

            monthly_balance=0,

            category_expenses=[],

            error="Unable to load money data."
        )

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass

@app.route("/add-money", methods=["POST"])
def add_money():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:

        user_id = session["user_id"]

        transaction_type = request.form.get("transaction_type")
        category = request.form.get("category")
        amount = request.form.get("amount")
        description = request.form.get("description")

        # Basic validation
        if not transaction_type or not category or not amount:
            return redirect(url_for("money"))

        amount = float(amount)

        if amount <= 0:
            return redirect(url_for("money"))

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO money_transactions
            (
                user_id,
                transaction_type,
                category,
                amount,
                description,
                transaction_date
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (
                user_id,
                transaction_type,
                category,
                amount,
                description
            )
        )

        connection.commit()

        return redirect(url_for("money"))

    except Exception as e:

        print("ADD MONEY ERROR:", repr(e))

        if connection:
            try:
                connection.rollback()
            except Exception:
                pass

        return redirect(url_for("money"))

    finally:

        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        if connection:
            try:
                connection.close()
            except Exception:
                pass
            
# =========================================================
# EDIT MONEY TRANSACTION
# =========================================================

@app.route(
    "/edit-money/<int:transaction_id>",
    methods=["GET", "POST"]
)
def edit_money(transaction_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        # =====================================================
        # UPDATE TRANSACTION
        # =====================================================

        if request.method == "POST":

            transaction_type = request.form.get(
                "transaction_type",
                ""
            ).strip()

            category = request.form.get(
                "category",
                ""
            ).strip()

            amount = request.form.get(
                "amount",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            allowed_types = [
                "Income",
                "Expense"
            ]

            if transaction_type not in allowed_types:

                return render_template(
                    "edit_money.html",
                    transaction={
                        "id": transaction_id,
                        "transaction_type": transaction_type,
                        "category": category,
                        "amount": amount,
                        "description": description
                    },
                    error="Please select a valid transaction type."
                )

            if not category or not amount:

                return render_template(
                    "edit_money.html",
                    transaction={
                        "id": transaction_id,
                        "transaction_type": transaction_type,
                        "category": category,
                        "amount": amount,
                        "description": description
                    },
                    error="Please fill in all required fields."
                )

            try:

                amount = float(amount)

            except (ValueError, TypeError):

                return render_template(
                    "edit_money.html",
                    transaction={
                        "id": transaction_id,
                        "transaction_type": transaction_type,
                        "category": category,
                        "amount": amount,
                        "description": description
                    },
                    error="Please enter a valid amount."
                )

            if amount <= 0:

                return render_template(
                    "edit_money.html",
                    transaction={
                        "id": transaction_id,
                        "transaction_type": transaction_type,
                        "category": category,
                        "amount": amount,
                        "description": description
                    },
                    error="Amount must be greater than zero."
                )

            cursor.execute(
                """
                UPDATE money_transactions
                SET
                    transaction_type = %s,
                    category = %s,
                    amount = %s,
                    description = %s
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    transaction_type,
                    category,
                    amount,
                    description,
                    transaction_id,
                    session["user_id"]
                )
            )

            connection.commit()

            return redirect(
                url_for("money")
            )

        # =====================================================
        # GET EXISTING TRANSACTION
        # =====================================================

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                transaction_type,
                category,
                amount,
                description,
                transaction_date
            FROM money_transactions
            WHERE id = %s
            AND user_id = %s
            """,
            (
                transaction_id,
                session["user_id"]
            )
        )

        transaction = cursor.fetchone()

        if not transaction:

            return redirect(
                url_for("money")
            )

        return render_template(
            "edit_money.html",
            transaction=transaction
        )

    except Exception as e:

        print(
            "EDIT MONEY ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

        return redirect(
            url_for("money")
        )

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass


# =========================================================
# DELETE MONEY TRANSACTION
# =========================================================

@app.route(
    "/delete-money/<int:transaction_id>"
)
def delete_money(transaction_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM money_transactions
            WHERE id = %s
            AND user_id = %s
            """,
            (
                transaction_id,
                session["user_id"]
            )
        )

        connection.commit()

    except Exception as e:

        print(
            "DELETE MONEY ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass

    return redirect(
        url_for("money")
    )
# =========================================================
# MY NOTES
# =========================================================

@app.route("/notes")
def notes():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM notes
            WHERE user_id = %s
            ORDER BY updated_at DESC
            """,
            (
                session["user_id"],
            )
        )

        notes_list = cursor.fetchall()

        return render_template(
            "notes.html",
            notes=notes_list
        )

    except Exception as e:

        print(
            "NOTES ERROR:",
            e
        )

        return render_template(
            "notes.html",
            notes=[],
            error="Unable to load your notes."
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# =========================================================
# ADD NOTE
# =========================================================

@app.route(
    "/add-note",
    methods=["POST"]
)
def add_note():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    title = request.form.get(
        "title",
        ""
    ).strip()

    content = request.form.get(
        "content",
        ""
    ).strip()

    if not title or not content:

        return redirect(
            url_for("notes")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO notes
            (
                user_id,
                title,
                content
            )
            VALUES
            (
                %s,
                %s,
                %s
            )
            """,
            (
                session["user_id"],
                title,
                content
            )
        )

        connection.commit()

    except Exception as e:

        print(
            "ADD NOTE ERROR:",
            e
        )

        if connection:
            connection.rollback()

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()

    return redirect(
        url_for("notes")
    )


# =========================================================
# EDIT NOTE
# =========================================================

@app.route(
    "/edit-note/<int:id>",
    methods=["GET", "POST"]
)
def edit_note(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "POST":

            title = request.form.get(
                "title",
                ""
            ).strip()

            content = request.form.get(
                "content",
                ""
            ).strip()

            if not title or not content:

                return render_template(
                    "edit_note.html",
                    note={
                        "id": id,
                        "title": title,
                        "content": content
                    },
                    error="Please fill in all fields."
                )

            cursor.execute(
                """
                UPDATE notes
                SET
                    title = %s,
                    content = %s
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    title,
                    content,
                    id,
                    session["user_id"]
                )
            )

            connection.commit()

            return redirect(
                url_for("notes")
            )

        cursor.execute(
            """
            SELECT *
            FROM notes
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        note = cursor.fetchone()

        if not note:

            return redirect(
                url_for("notes")
            )

        return render_template(
            "edit_note.html",
            note=note
        )

    except Exception as e:

        print(
            "EDIT NOTE ERROR:",
            e
        )

        if connection:
            connection.rollback()

        return redirect(
            url_for("notes")
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# =========================================================
# DELETE NOTE
# =========================================================

@app.route(
    "/delete-note/<int:id>"
)
def delete_note(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM notes
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        connection.commit()

    except Exception as e:

        print(
            "DELETE NOTE ERROR:",
            e
        )

        if connection:
            connection.rollback()

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()

    return redirect(
        url_for("notes")
    )


# =========================================================
# MOOD
# =========================================================

@app.route(
    "/mood",
    methods=["GET", "POST"]
)
def mood():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "POST":

            selected_mood = request.form.get(
                "mood",
                ""
            ).strip()

            note = request.form.get(
                "note",
                ""
            ).strip()

            allowed_moods = [
                "Happy",
                "Good",
                "Neutral",
                "Sad",
                "Stressed"
            ]

            if selected_mood not in allowed_moods:

                return redirect(
                    url_for("mood")
                )

            cursor.execute(
                """
                INSERT INTO moods
                (
                    user_id,
                    mood,
                    note
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    session["user_id"],
                    selected_mood,
                    note
                )
            )

            connection.commit()

            return redirect(
                url_for("mood")
            )

        cursor.execute(
            """
            SELECT *
            FROM moods
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (
                session["user_id"],
            )
        )

        moods = cursor.fetchall()

        return render_template(
            "mood.html",
            moods=moods
        )

    except Exception as e:

        print(
            "MOOD ERROR:",
            e
        )

        if connection:
            connection.rollback()

        return render_template(
            "mood.html",
            moods=[],
            error="Unable to load mood data."
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# =========================================================
# EDIT MOOD
# =========================================================

@app.route(
    "/edit-mood/<int:id>",
    methods=["GET", "POST"]
)
def edit_mood(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "POST":

            selected_mood = request.form.get(
                "mood",
                ""
            ).strip()

            note = request.form.get(
                "note",
                ""
            ).strip()

            allowed_moods = [
                "Happy",
                "Good",
                "Neutral",
                "Sad",
                "Stressed"
            ]

            if selected_mood not in allowed_moods:

                return redirect(
                    url_for("mood")
                )

            cursor.execute(
                """
                UPDATE moods
                SET
                    mood = %s,
                    note = %s
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    selected_mood,
                    note,
                    id,
                    session["user_id"]
                )
            )

            connection.commit()

            return redirect(
                url_for("mood")
            )

        cursor.execute(
            """
            SELECT *
            FROM moods
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        mood_record = cursor.fetchone()

        if not mood_record:

            return redirect(
                url_for("mood")
            )

        return render_template(
            "edit_mood.html",
            mood=mood_record
        )

    except Exception as e:

        print(
            "EDIT MOOD ERROR:",
            e
        )

        if connection:
            connection.rollback()

        return redirect(
            url_for("mood")
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# =========================================================
# DELETE MOOD
# =========================================================

@app.route(
    "/delete-mood/<int:id>"
)
def delete_mood(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM moods
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        connection.commit()

    except Exception as e:

        print(
            "DELETE MOOD ERROR:",
            e
        )

        if connection:
            connection.rollback()

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()

    return redirect(
        url_for("mood")
    )


# =========================================================
# STRESS
# =========================================================

@app.route(
    "/stress",
    methods=["GET", "POST"]
)
def stress():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "POST":

            stress_level = request.form.get(
                "stress_level",
                ""
            ).strip()

            note = request.form.get(
                "note",
                ""
            ).strip()

            allowed_levels = [
                "Low",
                "Moderate",
                "High",
                "Very High"
            ]

            if stress_level not in allowed_levels:

                return redirect(
                    url_for("stress")
                )

            cursor.execute(
                """
                INSERT INTO stress_records
                (
                    user_id,
                    stress_level,
                    note
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    session["user_id"],
                    stress_level,
                    note
                )
            )

            connection.commit()

            return redirect(
                url_for("stress")
            )

        cursor.execute(
            """
            SELECT *
            FROM stress_records
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (
                session["user_id"],
            )
        )

        stress_records = cursor.fetchall()

        return render_template(
            "stress.html",
            stress_records=stress_records
        )

    except Exception as e:

        print(
            "STRESS ERROR:",
            e
        )

        if connection:
            connection.rollback()

        return render_template(
            "stress.html",
            stress_records=[],
            error="Unable to load stress data."
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# =========================================================
# EDIT STRESS
# =========================================================

@app.route(
    "/edit-stress/<int:id>",
    methods=["GET", "POST"]
)
def edit_stress(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "POST":

            stress_level = request.form.get(
                "stress_level",
                ""
            ).strip()

            note = request.form.get(
                "note",
                ""
            ).strip()

            allowed_levels = [
                "Low",
                "Moderate",
                "High",
                "Very High"
            ]

            if stress_level not in allowed_levels:

                return redirect(
                    url_for("stress")
                )

            cursor.execute(
                """
                UPDATE stress_records
                SET
                    stress_level = %s,
                    note = %s
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    stress_level,
                    note,
                    id,
                    session["user_id"]
                )
            )

            connection.commit()

            return redirect(
                url_for("stress")
            )

        cursor.execute(
            """
            SELECT *
            FROM stress_records
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        record = cursor.fetchone()

        if not record:

            return redirect(
                url_for("stress")
            )

        return render_template(
            "edit_stress.html",
            stress=record
        )

    except Exception as e:

        print(
            "EDIT STRESS ERROR:",
            e
        )

        if connection:
            connection.rollback()

        return redirect(
            url_for("stress")
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# =========================================================
# DELETE STRESS
# =========================================================

@app.route(
    "/delete-stress/<int:id>"
)
def delete_stress(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM stress_records
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        connection.commit()

    except Exception as e:

        print(
            "DELETE STRESS ERROR:",
            e
        )

        if connection:
            connection.rollback()

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()

    return redirect(
        url_for("stress")
    )


# =========================================================
# SLEEP
# =========================================================

@app.route("/sleep", methods=["GET", "POST"])
def sleep():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # =====================================================
        # SAVE NEW SLEEP RECORD
        # =====================================================

        if request.method == "POST":

            sleep_date = request.form.get(
                "sleep_date", ""
            ).strip()

            bedtime = request.form.get(
                "bedtime", ""
            ).strip()

            wake_time = request.form.get(
                "wake_time", ""
            ).strip()

            sleep_quality = request.form.get(
                "sleep_quality", ""
            ).strip()

            note = request.form.get(
                "note", ""
            ).strip()

            allowed_quality = [
                "Excellent",
                "Good",
                "Average",
                "Poor",
                "Very Poor"
            ]

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------

            if not sleep_date:
                return render_template(
                    "sleep.html",
                    sleep_records=[],
                    error="Please select a sleep date."
                )

            if not bedtime:
                return render_template(
                    "sleep.html",
                    sleep_records=[],
                    error="Please enter bedtime."
                )

            if not wake_time:
                return render_template(
                    "sleep.html",
                    sleep_records=[],
                    error="Please enter wake-up time."
                )

            if sleep_quality not in allowed_quality:
                return render_template(
                    "sleep.html",
                    sleep_records=[],
                    error="Please select a valid sleep quality."
                )

            # -------------------------------------------------
            # VALIDATE DATE
            # -------------------------------------------------

            try:
                datetime.strptime(
                    sleep_date,
                    "%Y-%m-%d"
                )
            except ValueError:
                return render_template(
                    "sleep.html",
                    sleep_records=[],
                    error="Invalid sleep date."
                )

            # -------------------------------------------------
            # VALIDATE BEDTIME
            # -------------------------------------------------

            try:
                datetime.strptime(
                    bedtime,
                    "%H:%M"
                )
            except ValueError:
                return render_template(
                    "sleep.html",
                    sleep_records=[],
                    error="Invalid bedtime."
                )

            # -------------------------------------------------
            # VALIDATE WAKE TIME
            # -------------------------------------------------

            try:
                datetime.strptime(
                    wake_time,
                    "%H:%M"
                )
            except ValueError:
                return render_template(
                    "sleep.html",
                    sleep_records=[],
                    error="Invalid wake-up time."
                )

            # -------------------------------------------------
            # INSERT RECORD
            # -------------------------------------------------

            cursor.execute(
                """
                INSERT INTO sleep_records
                (
                    user_id,
                    sleep_date,
                    bedtime,
                    wake_time,
                    sleep_quality,
                    note
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    session["user_id"],
                    sleep_date,
                    bedtime,
                    wake_time,
                    sleep_quality,
                    note
                )
            )

            connection.commit()

            return redirect(
                url_for("sleep")
            )

        # =====================================================
        # LOAD SLEEP HISTORY
        # =====================================================

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                sleep_date,
                bedtime,
                wake_time,
                sleep_quality,
                note
            FROM sleep_records
            WHERE user_id = %s
            ORDER BY
                sleep_date DESC,
                id DESC
            """,
            (
                session["user_id"],
            )
        )

        sleep_records = cursor.fetchall()

        # Convert MySQL TIME values
        sleep_records = prepare_sleep_records(
            sleep_records
        )

        return render_template(
            "sleep.html",
            sleep_records=sleep_records
        )

    except Exception as e:

        print(
            "SLEEP ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

        return render_template(
            "sleep.html",
            sleep_records=[],
            error="Unable to load sleep data. "
                  "Please check your sleep_records table."
        )

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass


# =========================================================
# EDIT SLEEP
# =========================================================

@app.route(
    "/edit-sleep/<int:id>",
    methods=["GET", "POST"]
)
def edit_sleep(id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        # =====================================================
        # UPDATE SLEEP RECORD
        # =====================================================

        if request.method == "POST":

            sleep_date = request.form.get(
                "sleep_date", ""
            ).strip()

            bedtime = request.form.get(
                "bedtime", ""
            ).strip()

            wake_time = request.form.get(
                "wake_time", ""
            ).strip()

            sleep_quality = request.form.get(
                "sleep_quality", ""
            ).strip()

            note = request.form.get(
                "note", ""
            ).strip()

            allowed_quality = [
                "Excellent",
                "Good",
                "Average",
                "Poor",
                "Very Poor"
            ]

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------

            if not sleep_date:

                return render_template(
                    "edit_sleep.html",
                    error="Please select a sleep date.",
                    sleep_record={
                        "id": id,
                        "sleep_date": sleep_date,
                        "bedtime": bedtime,
                        "wake_time": wake_time,
                        "sleep_quality": sleep_quality,
                        "note": note
                    }
                )

            if not bedtime or not wake_time:

                return render_template(
                    "edit_sleep.html",
                    error="Please enter bedtime and wake-up time.",
                    sleep_record={
                        "id": id,
                        "sleep_date": sleep_date,
                        "bedtime": bedtime,
                        "wake_time": wake_time,
                        "sleep_quality": sleep_quality,
                        "note": note
                    }
                )

            if sleep_quality not in allowed_quality:

                return render_template(
                    "edit_sleep.html",
                    error="Please select a valid sleep quality.",
                    sleep_record={
                        "id": id,
                        "sleep_date": sleep_date,
                        "bedtime": bedtime,
                        "wake_time": wake_time,
                        "sleep_quality": sleep_quality,
                        "note": note
                    }
                )

            # -------------------------------------------------
            # VALIDATE DATE
            # -------------------------------------------------

            try:

                datetime.strptime(
                    sleep_date,
                    "%Y-%m-%d"
                )

            except ValueError:

                return render_template(
                    "edit_sleep.html",
                    error="Invalid sleep date.",
                    sleep_record={
                        "id": id,
                        "sleep_date": sleep_date,
                        "bedtime": bedtime,
                        "wake_time": wake_time,
                        "sleep_quality": sleep_quality,
                        "note": note
                    }
                )

            # -------------------------------------------------
            # VALIDATE BEDTIME
            # -------------------------------------------------

            try:

                datetime.strptime(
                    bedtime,
                    "%H:%M"
                )

            except ValueError:

                return render_template(
                    "edit_sleep.html",
                    error="Invalid bedtime.",
                    sleep_record={
                        "id": id,
                        "sleep_date": sleep_date,
                        "bedtime": bedtime,
                        "wake_time": wake_time,
                        "sleep_quality": sleep_quality,
                        "note": note
                    }
                )

            # -------------------------------------------------
            # VALIDATE WAKE TIME
            # -------------------------------------------------

            try:

                datetime.strptime(
                    wake_time,
                    "%H:%M"
                )

            except ValueError:

                return render_template(
                    "edit_sleep.html",
                    error="Invalid wake-up time.",
                    sleep_record={
                        "id": id,
                        "sleep_date": sleep_date,
                        "bedtime": bedtime,
                        "wake_time": wake_time,
                        "sleep_quality": sleep_quality,
                        "note": note
                    }
                )

            # -------------------------------------------------
            # UPDATE DATABASE
            # -------------------------------------------------

            cursor.execute(
                """
                UPDATE sleep_records
                SET
                    sleep_date = %s,
                    bedtime = %s,
                    wake_time = %s,
                    sleep_quality = %s,
                    note = %s
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    sleep_date,
                    bedtime,
                    wake_time,
                    sleep_quality,
                    note,
                    id,
                    session["user_id"]
                )
            )

            connection.commit()

            return redirect(
                url_for("sleep")
            )

        # =====================================================
        # GET EXISTING SLEEP RECORD
        # =====================================================

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                sleep_date,
                bedtime,
                wake_time,
                sleep_quality,
                note
            FROM sleep_records
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        sleep_record = cursor.fetchone()

        if not sleep_record:

            return redirect(
                url_for("sleep")
            )

        # Convert MySQL TIME values
        sleep_record["bedtime"] = convert_mysql_time(
            sleep_record.get("bedtime")
        )

        sleep_record["wake_time"] = convert_mysql_time(
            sleep_record.get("wake_time")
        )

        sleep_record["sleep_duration"] = calculate_sleep_duration(
            sleep_record.get("bedtime"),
            sleep_record.get("wake_time")
        )

        return render_template(
            "edit_sleep.html",
            sleep_record=sleep_record,
            sleep=sleep_record
        )

    except Exception as e:

        print(
            "EDIT SLEEP ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

        return redirect(
            url_for("sleep")
        )

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass


# =========================================================
# DELETE SLEEP
# =========================================================

@app.route(
    "/delete-sleep/<int:id>"
)
def delete_sleep(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM sleep_records
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        connection.commit()

    except Exception as e:

        print(
            "DELETE SLEEP ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass

    return redirect(
        url_for("sleep")
    )

# =========================================================
# ENERGY
# =========================================================

@app.route(
    "/energy",
    methods=["GET", "POST"]
)
def energy():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        # =====================================================
        # ADD ENERGY RECORD
        # =====================================================

        if request.method == "POST":

            energy_level = request.form.get(
                "energy_level",
                ""
            ).strip()

            note = request.form.get(
                "note",
                ""
            ).strip()

            allowed_levels = [
                "Very High",
                "High",
                "Moderate",
                "Low",
                "Very Low"
            ]

            if energy_level not in allowed_levels:

                return render_template(
                    "energy.html",
                    energy_records=[],
                    error="Please select a valid energy level."
                )

            cursor.execute(
                """
                INSERT INTO energy_records
                (
                    user_id,
                    energy_level,
                    note
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    session["user_id"],
                    energy_level,
                    note
                )
            )

            connection.commit()

            return redirect(
                url_for("energy")
            )

        # =====================================================
        # LOAD ENERGY HISTORY
        # =====================================================

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                energy_level,
                note,
                created_at
            FROM energy_records
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (
                session["user_id"],
            )
        )

        energy_records = cursor.fetchall()

        return render_template(
            "energy.html",
            energy_records=energy_records,
            name=session.get("user_name")
        )

    except Exception as e:

        print(
            "ENERGY ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

        return render_template(
            "energy.html",
            energy_records=[],
            name=session.get("user_name"),
            error="Unable to load energy data."
        )

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass


# =========================================================
# EDIT ENERGY
# =========================================================

@app.route(
    "/edit-energy/<int:id>",
    methods=["GET", "POST"]
)
def edit_energy(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        # =====================================================
        # UPDATE ENERGY
        # =====================================================

        if request.method == "POST":

            energy_level = request.form.get(
                "energy_level",
                ""
            ).strip()

            note = request.form.get(
                "note",
                ""
            ).strip()

            allowed_levels = [
                "Very High",
                "High",
                "Moderate",
                "Low",
                "Very Low"
            ]

            if energy_level not in allowed_levels:

                return render_template(
                    "edit_energy.html",
                    energy_record={
                        "id": id,
                        "energy_level": energy_level,
                        "note": note
                    },
                    error="Please select a valid energy level."
                )

            cursor.execute(
                """
                UPDATE energy_records
                SET
                    energy_level = %s,
                    note = %s
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    energy_level,
                    note,
                    id,
                    session["user_id"]
                )
            )

            connection.commit()

            return redirect(
                url_for("energy")
            )

        # =====================================================
        # GET EXISTING ENERGY RECORD
        # =====================================================

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                energy_level,
                note,
                created_at
            FROM energy_records
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        energy_record = cursor.fetchone()

        if not energy_record:

            return redirect(
                url_for("energy")
            )

        return render_template(
            "edit_energy.html",
            energy_record=energy_record
        )

    except Exception as e:

        print(
            "EDIT ENERGY ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

        return redirect(
            url_for("energy")
        )

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass


# =========================================================
# DELETE ENERGY
# =========================================================

@app.route(
    "/delete-energy/<int:id>"
)
def delete_energy(id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM energy_records
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        connection.commit()

    except Exception as e:

        print(
            "DELETE ENERGY ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()
            except Exception:
                pass

    finally:

        if cursor:

            try:
                cursor.close()
            except Exception:
                pass

        if connection:

            try:
                connection.close()
            except Exception:
                pass

    return redirect(
        url_for("energy")
    )
    
# =========================================================
# DAILY CHECK-IN
# =========================================================

@app.route("/daily-checkin", methods=["GET", "POST"])
def daily_checkin():

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        # =================================================
        # SAVE DAILY CHECK-IN
        # =================================================

        if request.method == "POST":

            checkin_date = request.form.get("checkin_date", "").strip()
            mood = request.form.get("mood", "").strip()
            stress_level = request.form.get("stress_level", "").strip()
            energy_level = request.form.get("energy_level", "").strip()
            sleep_hours = request.form.get("sleep_hours", "").strip()
            note = request.form.get("note", "").strip()

            allowed_moods = [
                "Happy",
                "Good",
                "Neutral",
                "Sad",
                "Stressed"
            ]

            allowed_stress = [
                "Low",
                "Moderate",
                "High",
                "Very High"
            ]

            allowed_energy = [
                "Very High",
                "High",
                "Moderate",
                "Low",
                "Very Low"
            ]

            # -----------------------------
            # VALIDATE DATE
            # -----------------------------

            if not checkin_date:

                return render_template(
                    "daily_checkin.html",
                    checkins=[],
                    name=session.get("user_name"),
                    error="Please select a date."
                )

            try:

                datetime.strptime(
                    checkin_date,
                    "%Y-%m-%d"
                )

            except ValueError:

                return render_template(
                    "daily_checkin.html",
                    checkins=[],
                    name=session.get("user_name"),
                    error="Invalid date."
                )

            # -----------------------------
            # VALIDATE MOOD
            # -----------------------------

            if mood not in allowed_moods:

                return render_template(
                    "daily_checkin.html",
                    checkins=[],
                    name=session.get("user_name"),
                    error="Please select a valid mood."
                )

            # -----------------------------
            # VALIDATE STRESS
            # -----------------------------

            if stress_level not in allowed_stress:

                return render_template(
                    "daily_checkin.html",
                    checkins=[],
                    name=session.get("user_name"),
                    error="Please select a valid stress level."
                )

            # -----------------------------
            # VALIDATE ENERGY
            # -----------------------------

            if energy_level not in allowed_energy:

                return render_template(
                    "daily_checkin.html",
                    checkins=[],
                    name=session.get("user_name"),
                    error="Please select a valid energy level."
                )

            # -----------------------------
            # VALIDATE SLEEP
            # -----------------------------

            try:

                sleep_hours = float(sleep_hours)

                if sleep_hours < 0 or sleep_hours > 24:

                    return render_template(
                        "daily_checkin.html",
                        checkins=[],
                        name=session.get("user_name"),
                        error="Sleep hours must be between 0 and 24."
                    )

            except (ValueError, TypeError):

                return render_template(
                    "daily_checkin.html",
                    checkins=[],
                    name=session.get("user_name"),
                    error="Please enter valid sleep hours."
                )

            # =================================================
            # INSERT INTO DATABASE
            # =================================================

            cursor.execute(
                """
                INSERT INTO daily_checkins
                (
                    user_id,
                    checkin_date,
                    mood,
                    stress_level,
                    energy_level,
                    sleep_hours,
                    note
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    session["user_id"],
                    checkin_date,
                    mood,
                    stress_level,
                    energy_level,
                    sleep_hours,
                    note
                )
            )

            connection.commit()

            print("DAILY CHECK-IN SAVED SUCCESSFULLY")

            return redirect(
                url_for("daily_checkin")
            )

        # =================================================
        # LOAD HISTORY
        # =================================================

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                checkin_date,
                mood,
                stress_level,
                energy_level,
                sleep_hours,
                note
            FROM daily_checkins
            WHERE user_id = %s
            ORDER BY checkin_date DESC, id DESC
            """,
            (
                session["user_id"],
            )
        )

        checkins = cursor.fetchall()

        print("CHECK-IN HISTORY:", checkins)

        return render_template(
            "daily_checkin.html",
            checkins=checkins,
            name=session.get("user_name")
        )

    except Exception as e:

        print(
            "DAILY CHECK-IN DATABASE ERROR:",
            repr(e)
        )

        if connection:

            try:
                connection.rollback()

            except Exception:
                pass

        return render_template(
            "daily_checkin.html",
            checkins=[],
            name=session.get("user_name"),
            error=f"Database error: {e}"
        )

    finally:

        if cursor:

            try:
                cursor.close()

            except Exception:
                pass

        if connection:

            try:
                connection.close()

            except Exception:
                pass

# =========================================================
# EDIT DAILY CHECK-IN
# =========================================================

@app.route("/edit-daily-checkin/<int:id>", methods=["GET", "POST"])
def edit_daily_checkin(id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # UPDATE RECORD
        if request.method == "POST":

            checkin_date = request.form.get("checkin_date", "").strip()
            mood = request.form.get("mood", "").strip()
            stress_level = request.form.get("stress_level", "").strip()
            energy_level = request.form.get("energy_level", "").strip()
            sleep_hours = request.form.get("sleep_hours", "").strip()
            note = request.form.get("note", "").strip()

            allowed_moods = [
                "Happy",
                "Good",
                "Neutral",
                "Sad",
                "Stressed"
            ]

            allowed_stress = [
                "Low",
                "Moderate",
                "High",
                "Very High"
            ]

            allowed_energy = [
                "Very High",
                "High",
                "Moderate",
                "Low",
                "Very Low"
            ]

            if not checkin_date:
                return redirect(url_for("daily_checkin"))

            if mood not in allowed_moods:
                return redirect(url_for("daily_checkin"))

            if stress_level not in allowed_stress:
                return redirect(url_for("daily_checkin"))

            if energy_level not in allowed_energy:
                return redirect(url_for("daily_checkin"))

            try:
                sleep_hours = float(sleep_hours)

                if sleep_hours < 0 or sleep_hours > 24:
                    return redirect(url_for("daily_checkin"))

            except (ValueError, TypeError):
                return redirect(url_for("daily_checkin"))

            cursor.execute(
                """
                UPDATE daily_checkins
                SET
                    checkin_date = %s,
                    mood = %s,
                    stress_level = %s,
                    energy_level = %s,
                    sleep_hours = %s,
                    note = %s
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    checkin_date,
                    mood,
                    stress_level,
                    energy_level,
                    sleep_hours,
                    note,
                    id,
                    session["user_id"]
                )
            )

            connection.commit()

            return redirect(url_for("daily_checkin"))

        # GET EXISTING RECORD
        cursor.execute(
            """
            SELECT
                id,
                user_id,
                checkin_date,
                mood,
                stress_level,
                energy_level,
                sleep_hours,
                note
            FROM daily_checkins
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        checkin = cursor.fetchone()

        if not checkin:
            return redirect(url_for("daily_checkin"))

        return render_template(
            "edit_daily_checkin.html",
            checkin=checkin
        )

    except Exception as e:

        print(
            "EDIT DAILY CHECK-IN ERROR:",
            repr(e)
        )

        if connection:
            try:
                connection.rollback()
            except Exception:
                pass

        return redirect(
            url_for("daily_checkin")
        )

    finally:

        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        if connection:
            try:
                connection.close()
            except Exception:
                pass


# =========================================================
# DELETE DAILY CHECK-IN
# =========================================================

@app.route("/delete-daily-checkin/<int:id>")
def delete_daily_checkin(id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM daily_checkins
            WHERE id = %s
            AND user_id = %s
            """,
            (
                id,
                session["user_id"]
            )
        )

        connection.commit()

    except Exception as e:

        print(
            "DELETE DAILY CHECK-IN ERROR:",
            repr(e)
        )

        if connection:
            try:
                connection.rollback()
            except Exception:
                pass

    finally:

        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

        if connection:
            try:
                connection.close()
            except Exception:
                pass

    return redirect(
        url_for("daily_checkin")
    )

@app.route('/progress')
def progress():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT checkin_date, mood, stress_level, energy_level, sleep_hours
        FROM daily_checkins
        WHERE user_id = %s
        ORDER BY checkin_date ASC
    """, (session['user_id'],))

    checkins = cursor.fetchall()

    cursor.close()
    conn.close()

    # Default values
    avg_sleep = 0
    avg_mood = 0
    avg_stress = 0
    avg_energy = 0

    if checkins:
        # Convert text values into numbers
        mood_values = {
            'Very Sad': 1,
            'Sad': 2,
            'Neutral': 3,
            'Good': 4,
            'Happy': 5
        }

        stress_values = {
            'Low': 1,
            'Moderate': 2,
            'High': 3,
            'Very High': 4
        }

        energy_values = {
            'Very Low': 1,
            'Low': 2,
            'Moderate': 3,
            'High': 4,
            'Very High': 5
        }

        total_sleep = 0
        total_mood = 0
        total_stress = 0
        total_energy = 0

        for checkin in checkins:
            total_sleep += float(checkin['sleep_hours'] or 0)

            total_mood += mood_values.get(checkin['mood'], 0)
            total_stress += stress_values.get(checkin['stress_level'], 0)
            total_energy += energy_values.get(checkin['energy_level'], 0)

        count = len(checkins)

        avg_sleep = round(total_sleep / count, 1)
        avg_mood = round(total_mood / count, 1)
        avg_stress = round(total_stress / count, 1)
        avg_energy = round(total_energy / count, 1)

    return render_template(
        'progress.html',
        checkins=checkins,
        avg_sleep=avg_sleep,
        avg_mood=avg_mood,
        avg_stress=avg_stress,
        avg_energy=avg_energy
    )

  
# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )

@app.route('/ai_insights')
def ai_insights():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT mood, stress_level, energy_level, sleep_hours
        FROM daily_checkins
        WHERE user_id = %s
        ORDER BY checkin_date DESC
        LIMIT 1
    """, (session['user_id'],))

    latest = cursor.fetchone()

    cursor.close()
    conn.close()

    if not latest:
        return render_template(
            'ai_insights.html',
            message="Complete a Daily Check-in first to get AI Insights."
        )

    mood = latest['mood']
    stress = latest['stress_level']
    energy = latest['energy_level']
    sleep = float(latest['sleep_hours'])

    insights = []

    # Sleep insight
    if sleep < 6:
        insights.append("😴 Your sleep is low. Try to get at least 7–8 hours of sleep.")
    elif sleep >= 7:
        insights.append("😴 Your sleep looks good. Keep maintaining a healthy sleep schedule.")
    else:
        insights.append("😴 Your sleep is moderate. Try to improve your sleeping routine.")

    # Stress insight
    if stress == "High" or stress == "Very High":
        insights.append("🧠 Your stress level is high. Consider taking short breaks, relaxing, or doing breathing exercises.")
    elif stress == "Moderate":
        insights.append("🧠 Your stress level is moderate. Try some relaxation activities.")
    else:
        insights.append("🧠 Your stress level is low. Keep maintaining your current routine.")

    # Energy insight
    if energy == "Low":
        insights.append("⚡ Your energy is low. Take proper rest and stay hydrated.")
    elif energy == "High" or energy == "Very High":
        insights.append("⚡ Your energy level is good. Use this energy for productive activities.")
    else:
        insights.append("⚡ Your energy level is moderate. Maintain a balanced routine.")

    # Mood insight
    if mood in ["Sad", "Very Sad", "Unhappy"]:
        insights.append("😊 Your mood seems low. Consider talking to someone you trust or doing an activity you enjoy.")
    elif mood in ["Happy", "Very Happy", "Good"]:
        insights.append("😊 Your mood looks positive. Keep doing activities that make you feel good.")
    else:
        insights.append("😊 Your mood is neutral. Pay attention to activities that improve your wellbeing.")

    return render_template(
        'ai_insights.html',
        mood=mood,
        stress=stress,
        energy=energy,
        sleep=sleep,
        insights=insights
    )
# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )