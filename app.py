import os
import calendar
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

from models import db, Admin, Student, Attendance, Fee
from utils import (
    whatsapp_link, fee_reminder_message, fee_receipt_message,
    attendance_alert_message, generate_receipt_pdf
)

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
basedir = os.path.abspath(os.path.dirname(__file__))
_db_url = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'instance', 'kc_coaching.db')}"
)
# Neon/Render sometimes hand out "postgres://" — SQLAlchemy needs "postgresql://"
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Admin, int(user_id))


# ---------- Auth ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin, remember=True)
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------- Dashboard ----------

@app.route("/")
@login_required
def dashboard():
    today = date.today()
    total_students = Student.query.filter_by(active=True).count()
    present_today = Attendance.query.filter_by(date=today, status="present").count()
    absent_today = Attendance.query.filter_by(date=today, status="absent").count()

    current_period = today.strftime("%Y-%m")
    fees_this_month = Fee.query.filter_by(period=current_period).all()
    total_due = sum(f.amount_due for f in fees_this_month)
    total_collected = sum(f.amount_paid for f in fees_this_month)
    pending_count = sum(1 for f in fees_this_month if f.status != "paid")

    recent_pending = (
        Fee.query.filter(Fee.status != "paid")
        .order_by(Fee.due_date.asc().nullslast())
        .limit(8)
        .all()
    )

    return render_template(
        "dashboard.html",
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today,
        not_marked=total_students - present_today - absent_today,
        total_due=total_due,
        total_collected=total_collected,
        pending_count=pending_count,
        recent_pending=recent_pending,
        current_period=current_period,
        today=today,
    )


# ---------- Students ----------

@app.route("/students")
@login_required
def students():
    batch_filter = request.args.get("batch", "")
    q = Student.query.filter_by(active=True)
    if batch_filter:
        q = q.filter_by(batch=batch_filter)
    all_students = q.order_by(Student.batch, Student.name).all()
    batches = sorted({s.batch for s in Student.query.filter_by(active=True).all()})
    return render_template("students.html", students=all_students, batches=batches, batch_filter=batch_filter)


@app.route("/students/new", methods=["GET", "POST"])
@login_required
def student_new():
    if request.method == "POST":
        s = Student(
            name=request.form["name"].strip(),
            batch=request.form["batch"].strip(),
            parent_name=request.form.get("parent_name", "").strip(),
            whatsapp_number=request.form["whatsapp_number"].strip(),
            fee_amount=float(request.form.get("fee_amount") or 0),
            fee_cycle=request.form.get("fee_cycle", "monthly"),
        )
        db.session.add(s)
        db.session.commit()
        flash(f"{s.name} added.", "success")
        return redirect(url_for("students"))
    return render_template("student_form.html", student=None)


@app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
def student_edit(student_id):
    s = db.get_or_404(Student, student_id)
    if request.method == "POST":
        s.name = request.form["name"].strip()
        s.batch = request.form["batch"].strip()
        s.parent_name = request.form.get("parent_name", "").strip()
        s.whatsapp_number = request.form["whatsapp_number"].strip()
        s.fee_amount = float(request.form.get("fee_amount") or 0)
        s.fee_cycle = request.form.get("fee_cycle", "monthly")
        db.session.commit()
        flash(f"{s.name} updated.", "success")
        return redirect(url_for("students"))
    return render_template("student_form.html", student=s)


@app.route("/students/<int:student_id>/deactivate", methods=["POST"])
@login_required
def student_deactivate(student_id):
    s = db.get_or_404(Student, student_id)
    s.active = False
    db.session.commit()
    flash(f"{s.name} deactivated.", "success")
    return redirect(url_for("students"))


# ---------- Attendance ----------

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    batch_filter = request.args.get("batch", "")
    selected_date = request.args.get("date", date.today().isoformat())
    d = datetime.strptime(selected_date, "%Y-%m-%d").date()

    if request.method == "POST":
        d = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        student_ids = request.form.getlist("student_id")
        for sid in student_ids:
            status = request.form.get(f"status_{sid}", "present")
            existing = Attendance.query.filter_by(student_id=sid, date=d).first()
            if existing:
                existing.status = status
            else:
                db.session.add(Attendance(student_id=sid, date=d, status=status))
        db.session.commit()
        flash(f"Attendance saved for {d.strftime('%d-%b-%Y')}.", "success")
        return redirect(url_for("attendance", batch=batch_filter, date=d.isoformat()))

    q = Student.query.filter_by(active=True)
    if batch_filter:
        q = q.filter_by(batch=batch_filter)
    all_students = q.order_by(Student.name).all()
    batches = sorted({s.batch for s in Student.query.filter_by(active=True).all()})

    existing_marks = {
        a.student_id: a.status
        for a in Attendance.query.filter_by(date=d).all()
    }

    return render_template(
        "attendance.html",
        students=all_students,
        batches=batches,
        batch_filter=batch_filter,
        selected_date=d.isoformat(),
        existing_marks=existing_marks,
    )


@app.route("/attendance/notify/<int:student_id>/<status>/<day>")
@login_required
def attendance_notify(student_id, status, day):
    s = db.get_or_404(Student, student_id)
    d = datetime.strptime(day, "%Y-%m-%d").date()
    msg = attendance_alert_message(s, status, d)
    return redirect(whatsapp_link(s.whatsapp_number, msg))


@app.route("/attendance/report")
@login_required
def attendance_report():
    period = request.args.get("period", date.today().strftime("%Y-%m"))
    year, month = map(int, period.split("-"))
    days_in_month = calendar.monthrange(year, month)[1]

    all_students = Student.query.filter_by(active=True).order_by(Student.batch, Student.name).all()
    records = Attendance.query.filter(
        db.extract("year", Attendance.date) == year,
        db.extract("month", Attendance.date) == month,
    ).all()

    summary = {}
    for s in all_students:
        s_records = [r for r in records if r.student_id == s.id]
        present = sum(1 for r in s_records if r.status == "present")
        absent = sum(1 for r in s_records if r.status == "absent")
        marked = present + absent
        pct = round((present / marked) * 100, 1) if marked else 0
        summary[s.id] = {"student": s, "present": present, "absent": absent, "pct": pct}

    return render_template(
        "reports.html",
        summary=summary,
        period=period,
        days_in_month=days_in_month,
        report_type="attendance",
    )


# ---------- Fees ----------

@app.route("/fees")
@login_required
def fees():
    period = request.args.get("period", date.today().strftime("%Y-%m"))
    status_filter = request.args.get("status", "")

    q = Fee.query.filter_by(period=period)
    if status_filter:
        q = q.filter_by(status=status_filter)
    fee_list = q.join(Student).order_by(Student.batch, Student.name).all()

    students_without_fee = (
        Student.query.filter_by(active=True)
        .filter(~Student.fees.any(Fee.period == period))
        .all()
    )

    return render_template(
        "fees.html",
        fees=fee_list,
        period=period,
        status_filter=status_filter,
        students_without_fee=students_without_fee,
    )


@app.route("/fees/generate", methods=["POST"])
@login_required
def fees_generate():
    """Bulk-create pending Fee rows for all active students for a given period."""
    period = request.form["period"]
    due_day = request.form.get("due_date")
    due_date_obj = datetime.strptime(due_day, "%Y-%m-%d").date() if due_day else None

    created = 0
    for s in Student.query.filter_by(active=True).all():
        exists = Fee.query.filter_by(student_id=s.id, period=period).first()
        if not exists:
            db.session.add(Fee(
                student_id=s.id, period=period, amount_due=s.fee_amount,
                amount_paid=0, status="pending", due_date=due_date_obj,
            ))
            created += 1
    db.session.commit()
    flash(f"Generated {created} fee entries for {period}.", "success")
    return redirect(url_for("fees", period=period))


@app.route("/fees/<int:fee_id>/pay", methods=["POST"])
@login_required
def fees_pay(fee_id):
    fee = db.get_or_404(Fee, fee_id)
    amount = float(request.form.get("amount_paid") or 0)
    fee.amount_paid = amount
    fee.recompute_status()
    if fee.status == "paid":
        fee.paid_date = date.today()
    db.session.commit()
    flash("Payment recorded.", "success")
    return redirect(url_for("fees", period=fee.period))


@app.route("/fees/<int:fee_id>/remind")
@login_required
def fees_remind(fee_id):
    fee = db.get_or_404(Fee, fee_id)
    s = fee.student
    msg = fee_reminder_message(s, fee)
    return redirect(whatsapp_link(s.whatsapp_number, msg))


@app.route("/fees/<int:fee_id>/receipt-msg")
@login_required
def fees_receipt_msg(fee_id):
    fee = db.get_or_404(Fee, fee_id)
    s = fee.student
    msg = fee_receipt_message(s, fee)
    return redirect(whatsapp_link(s.whatsapp_number, msg))


@app.route("/fees/<int:fee_id>/receipt.pdf")
@login_required
def fees_receipt_pdf(fee_id):
    fee = db.get_or_404(Fee, fee_id)
    s = fee.student
    buf = generate_receipt_pdf(s, fee)
    filename = f"receipt_{s.name.replace(' ', '_')}_{fee.period}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=False, download_name=filename)


# ---------- Reports (fee collection) ----------

@app.route("/reports")
@login_required
def reports():
    period = request.args.get("period", date.today().strftime("%Y-%m"))
    fee_list = Fee.query.filter_by(period=period).join(Student).order_by(Student.batch, Student.name).all()
    total_due = sum(f.amount_due for f in fee_list)
    total_collected = sum(f.amount_paid for f in fee_list)
    return render_template(
        "reports.html",
        report_type="fees",
        fee_list=fee_list,
        period=period,
        total_due=total_due,
        total_collected=total_collected,
    )


# ---------- PWA ----------

@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")


@app.route("/service-worker.js")
def service_worker():
    return app.send_static_file("service-worker.js")


# ---------- CLI: create admin ----------

@app.cli.command("create-admin")
def create_admin():
    """Usage: flask create-admin"""
    username = input("Username: ").strip()
    password = input("Password: ").strip()
    if Admin.query.filter_by(username=username).first():
        print("Admin already exists.")
        return
    admin = Admin(username=username)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Admin '{username}' created.")


with app.app_context():
    db.create_all()
    if not Admin.query.first():
        # First-run convenience default — change immediately after first login
        default_admin = Admin(username="admin")
        default_admin.set_password("changeme123")
        db.session.add(default_admin)
        db.session.commit()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
