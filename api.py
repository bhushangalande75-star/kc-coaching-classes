"""
JSON API for the KC Coaching Classes Flutter app. Separate from the
server-rendered web routes in app.py — token-authenticated (Bearer header)
instead of session cookies, since a mobile app has no browser session.
"""
import os
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify, current_app, send_file, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from models import db, Admin, Student, Batch, Attendance, Fee, DateOverride, normalize_indian_mobile
from services import (
    previous_period_str, next_period_str, compute_due_and_note,
    generate_fees_for_period, maybe_auto_generate_next_month, get_share_serializer,
)
from utils import (
    fee_reminder_message, fee_receipt_message, attendance_share_message,
    generate_receipt_pdf, generate_attendance_pdf,
)

api = Blueprint("api", __name__, url_prefix="/api")

TOKEN_MAX_AGE = 60 * 60 * 24 * 90  # 90 days — long-lived since this is a single-teacher app


def get_api_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="mobile-api-token")


def api_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth[len("Bearer "):]
        try:
            data = get_api_serializer().loads(token, max_age=TOKEN_MAX_AGE)
        except SignatureExpired:
            return jsonify({"error": "Session expired, please log in again"}), 401
        except BadSignature:
            return jsonify({"error": "Invalid token"}), 401
        admin = db.session.get(Admin, data.get("admin_id"))
        if not admin:
            return jsonify({"error": "Invalid token"}), 401
        request.current_admin = admin
        return f(*args, **kwargs)
    return wrapper


# ---------- Serializers ----------

def student_to_dict(s):
    return {
        "id": s.id, "name": s.name, "batch_id": s.batch_id, "batch_name": s.batch_name(),
        "parent_name": s.parent_name, "whatsapp_number": s.whatsapp_number,
        "fee_amount": s.fee_amount, "fee_cycle": s.fee_cycle,
        "join_date": s.join_date.isoformat() if s.join_date else None, "active": s.active,
    }


def batch_to_dict(b):
    return {
        "id": b.id, "name": b.name, "default_fee": b.default_fee,
        "student_count": b.active_student_count(),
    }


def fee_to_dict(f):
    return {
        "id": f.id, "student_id": f.student_id, "student_name": f.student.name,
        "batch_name": f.student.batch_name(), "period": f.period,
        "amount_due": f.amount_due, "amount_paid": f.amount_paid, "balance": f.balance(),
        "status": f.status, "note": f.note,
        "paid_date": f.paid_date.isoformat() if f.paid_date else None,
        "due_date": f.due_date.isoformat() if f.due_date else None,
    }


# ---------- Auth ----------

@api.route("/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    admin = Admin.query.filter_by(username=username).first()
    if not admin or not admin.check_password(password):
        return jsonify({"error": "Invalid username or password"}), 401
    token = get_api_serializer().dumps({"admin_id": admin.id})
    return jsonify({"token": token, "username": admin.username})


@api.route("/forgot-password", methods=["POST"])
def api_forgot_password():
    data = request.get_json(force=True, silent=True) or {}
    recovery_key = data.get("recovery_key") or ""
    new_password = data.get("new_password") or ""
    admin_recovery_key = os.environ.get("ADMIN_RECOVERY_KEY", "")
    if not admin_recovery_key or recovery_key != admin_recovery_key:
        return jsonify({"error": "Incorrect recovery key"}), 401
    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400
    admin = Admin.query.first()
    admin.set_password(new_password)
    db.session.commit()
    return jsonify({"ok": True})


# ---------- Dashboard ----------

@api.route("/dashboard", methods=["GET"])
@api_login_required
def api_dashboard():
    maybe_auto_generate_next_month()
    today = date.today()
    total_students = Student.query.filter_by(active=True).count()
    present_today = Attendance.query.filter_by(date=today, status="present").count()
    absent_today = Attendance.query.filter_by(date=today, status="absent").count()

    current_period = today.strftime("%Y-%m")
    fees_this_month = Fee.query.filter_by(period=current_period).all()
    total_due = sum(f.amount_due for f in fees_this_month)
    total_collected = sum(f.amount_paid for f in fees_this_month)
    pending_count = sum(1 for f in fees_this_month if f.status not in ("paid", "waived"))

    recent_pending = (
        Fee.query.filter(Fee.status.notin_(["paid", "waived"]))
        .order_by(Fee.due_date.asc().nullslast())
        .limit(8)
        .all()
    )

    attendance_labels, attendance_present, attendance_absent = [], [], []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        p = Attendance.query.filter_by(date=d, status="present").count()
        a = Attendance.query.filter_by(date=d, status="absent").count()
        attendance_labels.append(d.strftime("%d %b"))
        attendance_present.append(p)
        attendance_absent.append(a)

    fee_labels, fee_due, fee_collected = [], [], []
    y, m = today.year, today.month
    months = []
    for i in range(5, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append((yy, mm))
    for yy, mm in months:
        period_str = f"{yy:04d}-{mm:02d}"
        month_fees = Fee.query.filter_by(period=period_str).all()
        fee_labels.append(datetime(yy, mm, 1).strftime("%b %Y"))
        fee_due.append(sum(f.amount_due for f in month_fees))
        fee_collected.append(sum(f.amount_paid for f in month_fees))

    return jsonify({
        "total_students": total_students,
        "present_today": present_today,
        "absent_today": absent_today,
        "not_marked": total_students - present_today - absent_today,
        "total_due": total_due,
        "total_collected": total_collected,
        "pending_count": pending_count,
        "recent_pending": [fee_to_dict(f) for f in recent_pending],
        "current_period": current_period,
        "today": today.isoformat(),
        "is_holiday_today": DateOverride.is_holiday(today),
        "holiday_reason": DateOverride.get_reason(today),
        "attendance_chart": {
            "labels": attendance_labels, "present": attendance_present, "absent": attendance_absent,
        },
        "fee_chart": {"labels": fee_labels, "due": fee_due, "collected": fee_collected},
    })


# ---------- Batches ----------

@api.route("/batches", methods=["GET"])
@api_login_required
def api_batches():
    return jsonify([batch_to_dict(b) for b in Batch.query.order_by(Batch.name).all()])


@api.route("/batches", methods=["POST"])
@api_login_required
def api_batch_create():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    if Batch.query.filter_by(name=name).first():
        return jsonify({"error": f"Batch '{name}' already exists"}), 400
    b = Batch(name=name, default_fee=data.get("default_fee"))
    db.session.add(b)
    db.session.commit()
    return jsonify(batch_to_dict(b)), 201


@api.route("/batches/<int:batch_id>", methods=["PUT"])
@api_login_required
def api_batch_update(batch_id):
    b = db.session.get(Batch, batch_id)
    if not b:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    new_name = (data.get("name") or b.name).strip()
    clash = Batch.query.filter(Batch.name == new_name, Batch.id != b.id).first()
    if clash:
        return jsonify({"error": f"Batch '{new_name}' already exists"}), 400
    b.name = new_name
    if "default_fee" in data:
        b.default_fee = data["default_fee"]
    db.session.commit()
    return jsonify(batch_to_dict(b))


@api.route("/batches/<int:batch_id>", methods=["DELETE"])
@api_login_required
def api_batch_delete(batch_id):
    b = db.session.get(Batch, batch_id)
    if not b:
        return jsonify({"error": "Not found"}), 404
    if b.active_student_count() > 0:
        return jsonify({"error": f"'{b.name}' still has students assigned — reassign them first"}), 400
    db.session.delete(b)
    db.session.commit()
    return jsonify({"ok": True})


# ---------- Students ----------

@api.route("/students", methods=["GET"])
@api_login_required
def api_students():
    batch_id = request.args.get("batch", type=int)
    q = Student.query.filter_by(active=True)
    if batch_id:
        q = q.filter_by(batch_id=batch_id)
    students = q.join(Batch, isouter=True).order_by(Batch.name, Student.name).all()
    return jsonify([student_to_dict(s) for s in students])


@api.route("/students", methods=["POST"])
@api_login_required
def api_student_create():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    batch_id = data.get("batch_id")
    whatsapp = normalize_indian_mobile(data.get("whatsapp_number", ""))
    if not name or not batch_id or len(whatsapp) != 10:
        return jsonify({"error": "name, batch_id, and a valid 10-digit whatsapp_number are required"}), 400
    s = Student(
        name=name, batch_id=batch_id, parent_name=(data.get("parent_name") or "").strip(),
        whatsapp_number=whatsapp, fee_amount=float(data.get("fee_amount") or 0),
        fee_cycle=data.get("fee_cycle", "monthly"),
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(student_to_dict(s)), 201


@api.route("/students/<int:student_id>", methods=["PUT"])
@api_login_required
def api_student_update(student_id):
    s = db.session.get(Student, student_id)
    if not s:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    if "name" in data:
        s.name = data["name"].strip()
    if "batch_id" in data:
        s.batch_id = data["batch_id"]
    if "parent_name" in data:
        s.parent_name = (data["parent_name"] or "").strip()
    if "whatsapp_number" in data:
        s.whatsapp_number = normalize_indian_mobile(data["whatsapp_number"])
    if "fee_amount" in data:
        s.fee_amount = float(data["fee_amount"] or 0)
    if "fee_cycle" in data:
        s.fee_cycle = data["fee_cycle"]
    db.session.commit()
    return jsonify(student_to_dict(s))


@api.route("/students/<int:student_id>/deactivate", methods=["POST"])
@api_login_required
def api_student_deactivate(student_id):
    s = db.session.get(Student, student_id)
    if not s:
        return jsonify({"error": "Not found"}), 404
    s.active = False
    db.session.commit()
    return jsonify({"ok": True})


# ---------- Attendance ----------

@api.route("/attendance", methods=["GET"])
@api_login_required
def api_attendance_get():
    date_str = request.args.get("date", date.today().isoformat())
    batch_id = request.args.get("batch", type=int)
    d = datetime.strptime(date_str, "%Y-%m-%d").date()

    q = Student.query.filter_by(active=True)
    if batch_id:
        q = q.filter_by(batch_id=batch_id)
    students = q.order_by(Student.name).all()

    marks = {a.student_id: a.status for a in Attendance.query.filter_by(date=d).all()}

    return jsonify({
        "date": d.isoformat(),
        "is_sunday": d.weekday() == 6,
        "is_holiday": DateOverride.is_holiday(d),
        "holiday_reason": DateOverride.get_reason(d),
        "is_override": DateOverride.query.filter_by(date=d).first() is not None,
        "students": [{**student_to_dict(s), "status": marks.get(s.id)} for s in students],
    })


@api.route("/attendance", methods=["POST"])
@api_login_required
def api_attendance_save():
    data = request.get_json(force=True, silent=True) or {}
    d = datetime.strptime(data["date"], "%Y-%m-%d").date()
    if DateOverride.is_holiday(d):
        return jsonify({"error": "This date is marked as a holiday. Mark it as a working day first."}), 400
    marks = data.get("marks", {})
    for sid, status in marks.items():
        existing = Attendance.query.filter_by(student_id=int(sid), date=d).first()
        if existing:
            existing.status = status
        else:
            db.session.add(Attendance(student_id=int(sid), date=d, status=status))
    db.session.commit()
    return jsonify({"ok": True})


@api.route("/attendance/bulk", methods=["POST"])
@api_login_required
def api_attendance_bulk():
    data = request.get_json(force=True, silent=True) or {}
    d = datetime.strptime(data["date"], "%Y-%m-%d").date()
    status = data["status"]
    batch_id = data.get("batch_id")
    if DateOverride.is_holiday(d):
        return jsonify({"error": "This date is marked as a holiday."}), 400
    q = Student.query.filter_by(active=True)
    if batch_id:
        q = q.filter_by(batch_id=batch_id)
    students = q.all()
    for s in students:
        existing = Attendance.query.filter_by(student_id=s.id, date=d).first()
        if existing:
            existing.status = status
        else:
            db.session.add(Attendance(student_id=s.id, date=d, status=status))
    db.session.commit()
    return jsonify({"ok": True, "count": len(students)})


@api.route("/attendance/day-status", methods=["POST"])
@api_login_required
def api_attendance_day_status():
    data = request.get_json(force=True, silent=True) or {}
    d = datetime.strptime(data["date"], "%Y-%m-%d").date()
    action = data["action"]  # 'holiday' or 'working'
    reason = (data.get("reason") or "").strip()
    existing = DateOverride.query.filter_by(date=d).first()
    if existing:
        existing.status = action
        if reason:
            existing.reason = reason
    else:
        db.session.add(DateOverride(date=d, status=action, reason=reason or None))
    db.session.commit()
    return jsonify({"ok": True})


@api.route("/attendance/report", methods=["GET"])
@api_login_required
def api_attendance_report():
    period = request.args.get("period", date.today().strftime("%Y-%m"))
    year, month = map(int, period.split("-"))
    all_students = (
        Student.query.filter_by(active=True).join(Batch, isouter=True)
        .order_by(Batch.name, Student.name).all()
    )
    records = Attendance.query.filter(
        db.extract("year", Attendance.date) == year,
        db.extract("month", Attendance.date) == month,
    ).all()
    rows = []
    for s in all_students:
        s_records = [r for r in records if r.student_id == s.id]
        present = sum(1 for r in s_records if r.status == "present")
        absent = sum(1 for r in s_records if r.status == "absent")
        marked = present + absent
        pct = round((present / marked) * 100, 1) if marked else 0
        rows.append({"student": student_to_dict(s), "present": present, "absent": absent, "pct": pct})
    return jsonify({"period": period, "rows": rows})


@api.route("/attendance/share/<int:student_id>", methods=["GET"])
@api_login_required
def api_attendance_share(student_id):
    period = request.args.get("period", date.today().strftime("%Y-%m"))
    s = db.session.get(Student, student_id)
    if not s:
        return jsonify({"error": "Not found"}), 404
    token = get_share_serializer().dumps({"sid": s.id, "period": period})
    share_link = url_for("shared_attendance_pdf", token=token, _external=True)
    message = attendance_share_message(s, period, share_link)
    return jsonify({"phone": s.whatsapp_full(), "message": message, "pdf_url": share_link})


@api.route("/attendance/notify/<int:student_id>", methods=["GET"])
@api_login_required
def api_attendance_notify(student_id):
    status = request.args.get("status", "absent")
    day_str = request.args.get("date", date.today().isoformat())
    d = datetime.strptime(day_str, "%Y-%m-%d").date()
    s = db.session.get(Student, student_id)
    if not s:
        return jsonify({"error": "Not found"}), 404
    from utils import attendance_alert_message
    return jsonify({"phone": s.whatsapp_full(), "message": attendance_alert_message(s, status, d)})


# ---------- Fees ----------

@api.route("/fees", methods=["GET"])
@api_login_required
def api_fees():
    period = request.args.get("period", date.today().strftime("%Y-%m"))
    status = request.args.get("status", "")
    batch_id = request.args.get("batch", type=int)

    q = Fee.query.filter_by(period=period)
    if status:
        q = q.filter_by(status=status)
    q = q.join(Student).join(Batch, isouter=True)
    if batch_id:
        q = q.filter(Student.batch_id == batch_id)
    fee_list = q.order_by(Batch.name, Student.name).all()

    swf_q = Student.query.filter_by(active=True).filter(~Student.fees.any(Fee.period == period))
    if batch_id:
        swf_q = swf_q.filter_by(batch_id=batch_id)
    students_without_fee = swf_q.all()

    return jsonify({
        "period": period,
        "fees": [fee_to_dict(f) for f in fee_list],
        "students_without_fee": [student_to_dict(s) for s in students_without_fee],
    })


@api.route("/fees/generate", methods=["POST"])
@api_login_required
def api_fees_generate():
    data = request.get_json(force=True, silent=True) or {}
    period = data["period"]
    due_date_str = data.get("due_date")
    due_date_obj = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None
    created = generate_fees_for_period(period, due_date_obj)
    return jsonify({"ok": True, "created": created})


@api.route("/fees/generate-next-month", methods=["POST"])
@api_login_required
def api_fees_generate_next_month():
    current_period = date.today().strftime("%Y-%m")
    period = next_period_str(current_period)
    created = generate_fees_for_period(period)
    return jsonify({"ok": True, "created": created, "period": period})


@api.route("/fees/<int:fee_id>/pay", methods=["POST"])
@api_login_required
def api_fees_pay(fee_id):
    fee = db.session.get(Fee, fee_id)
    if not fee:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    fee.amount_paid = float(data.get("amount_paid") or 0)
    fee.recompute_status()
    if fee.status == "paid":
        fee.paid_date = date.today()
    db.session.commit()
    return jsonify(fee_to_dict(fee))


@api.route("/fees/<int:fee_id>/mark-paid", methods=["POST"])
@api_login_required
def api_fees_mark_paid(fee_id):
    fee = db.session.get(Fee, fee_id)
    if not fee:
        return jsonify({"error": "Not found"}), 404
    fee.amount_paid = fee.amount_due
    fee.status = "paid"
    fee.paid_date = date.today()
    db.session.commit()
    return jsonify(fee_to_dict(fee))


@api.route("/fees/bulk-pay", methods=["POST"])
@api_login_required
def api_fees_bulk_pay():
    data = request.get_json(force=True, silent=True) or {}
    fee_ids = data.get("fee_ids", [])
    count = 0
    for fid in fee_ids:
        fee = db.session.get(Fee, int(fid))
        if fee:
            fee.amount_paid = fee.amount_due
            fee.status = "paid"
            fee.paid_date = date.today()
            count += 1
    db.session.commit()
    return jsonify({"ok": True, "count": count})


@api.route("/fees/<int:fee_id>/waive", methods=["POST"])
@api_login_required
def api_fees_waive(fee_id):
    fee = db.session.get(Fee, fee_id)
    if not fee:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(silent=True) or {}
    fee.status = "waived"
    note = (data.get("note") or "").strip()
    if note:
        fee.note = note
    db.session.commit()
    return jsonify(fee_to_dict(fee))


@api.route("/fees/<int:fee_id>/remind", methods=["GET"])
@api_login_required
def api_fees_remind(fee_id):
    fee = db.session.get(Fee, fee_id)
    if not fee:
        return jsonify({"error": "Not found"}), 404
    s = fee.student
    return jsonify({"phone": s.whatsapp_full(), "message": fee_reminder_message(s, fee)})


@api.route("/fees/<int:fee_id>/receipt-msg", methods=["GET"])
@api_login_required
def api_fees_receipt_msg(fee_id):
    fee = db.session.get(Fee, fee_id)
    if not fee:
        return jsonify({"error": "Not found"}), 404
    s = fee.student
    return jsonify({"phone": s.whatsapp_full(), "message": fee_receipt_message(s, fee)})


@api.route("/fees/<int:fee_id>/receipt.pdf", methods=["GET"])
@api_login_required
def api_fee_receipt_pdf(fee_id):
    fee = db.session.get(Fee, fee_id)
    if not fee:
        return jsonify({"error": "Not found"}), 404
    buf = generate_receipt_pdf(fee.student, fee)
    filename = f"receipt_{fee.student.name.replace(' ', '_')}_{fee.period}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=False, download_name=filename)


@api.route("/fees/ledger", methods=["GET"])
@api_login_required
def api_fees_ledger():
    batch_id = request.args.get("batch", type=int)
    months = request.args.get("months", 6, type=int)
    months = max(1, min(months, 12))

    today = date.today()
    periods = []
    y, m = today.year, today.month
    for i in range(months - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        periods.append(f"{yy:04d}-{mm:02d}")

    q = Student.query.filter_by(active=True).join(Batch, isouter=True)
    if batch_id:
        q = q.filter(Student.batch_id == batch_id)
    students = q.order_by(Batch.name, Student.name).all()

    fee_map = {}
    for f in Fee.query.filter(Fee.period.in_(periods)).all():
        fee_map[(f.student_id, f.period)] = f

    rows = []
    for s in students:
        cells = []
        outstanding = 0.0
        for p in periods:
            f = fee_map.get((s.id, p))
            cells.append(fee_to_dict(f) if f else None)
            if f and f.status in ("pending", "partial"):
                outstanding += f.balance()
        rows.append({"student": student_to_dict(s), "cells": cells, "outstanding": outstanding})

    return jsonify({"periods": periods, "rows": rows})
