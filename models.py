from datetime import date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def normalize_indian_mobile(raw):
    """Strip everything to digits, drop a leading 91 if present, keep the last 10 digits.
    Storage is always the bare 10-digit number - country code is applied only when
    building a wa.me link, since this app is India-only by default."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


class Admin(UserMixin, db.Model):
    """Single teacher/admin login for KC Coaching Classes."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Batch(db.Model):
    """A class/batch (e.g. '10th Science', 'Sr Kg'). Students are allocated to one."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    default_fee = db.Column(db.Float, nullable=True)
    created_date = db.Column(db.Date, default=date.today)

    students = db.relationship("Student", backref="batch", lazy="dynamic")

    def active_student_count(self):
        return self.students.filter_by(active=True).count()


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"), nullable=True)
    parent_name = db.Column(db.String(120))
    whatsapp_number = db.Column(db.String(10), nullable=False)  # bare 10-digit number, no country code
    fee_amount = db.Column(db.Float, nullable=False, default=0)
    fee_cycle = db.Column(db.String(20), nullable=False, default="monthly")  # monthly / one-time
    join_date = db.Column(db.Date, default=date.today)
    active = db.Column(db.Boolean, default=True)

    attendances = db.relationship("Attendance", backref="student", cascade="all, delete-orphan")
    fees = db.relationship("Fee", backref="student", cascade="all, delete-orphan")

    def whatsapp_full(self):
        """Full number with India's country code, ready for a wa.me link."""
        return "91" + normalize_indian_mobile(self.whatsapp_number)

    def batch_name(self):
        return self.batch.name if self.batch else "Unassigned"


class DateOverride(db.Model):
    """Explicit holiday/working-day override for a specific date. Sunday is a
    holiday by default without needing a row here — this table only stores
    exceptions: an ad-hoc holiday on a normal day, or tuition held on a Sunday."""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    status = db.Column(db.String(10), nullable=False)  # 'holiday' or 'working'
    reason = db.Column(db.String(200), nullable=True)

    @staticmethod
    def is_holiday(d):
        override = DateOverride.query.filter_by(date=d).first()
        if override:
            return override.status == "holiday"
        return d.weekday() == 6  # Sunday, default holiday

    @staticmethod
    def get_reason(d):
        override = DateOverride.query.filter_by(date=d).first()
        if override and override.reason:
            return override.reason
        if d.weekday() == 6:
            return "Sunday"
        return None


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(10), nullable=False, default="present")  # present / absent

    __table_args__ = (db.UniqueConstraint("student_id", "date", name="uq_student_date"),)


class Fee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    period = db.Column(db.String(20), nullable=False)   # e.g. "2026-08"
    amount_due = db.Column(db.Float, nullable=False, default=0)
    amount_paid = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(15), nullable=False, default="pending")  # pending / partial / paid / waived
    paid_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    note = db.Column(db.String(200), nullable=True)  # e.g. reason for waiver/discount

    __table_args__ = (db.UniqueConstraint("student_id", "period", name="uq_student_period"),)

    def balance(self):
        if self.status == "waived":
            return 0.0
        return round(self.amount_due - self.amount_paid, 2)

    def recompute_status(self):
        if self.status == "waived":
            return
        if self.amount_paid <= 0:
            self.status = "pending"
        elif self.amount_paid < self.amount_due:
            self.status = "partial"
        else:
            self.status = "paid"
