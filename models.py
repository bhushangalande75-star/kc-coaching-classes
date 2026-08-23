from datetime import date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Admin(UserMixin, db.Model):
    """Single teacher/admin login for KC Coaching Classes."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    batch = db.Column(db.String(80), nullable=False)          # e.g. "10th Science", "Batch A"
    parent_name = db.Column(db.String(120))
    whatsapp_number = db.Column(db.String(20), nullable=False)  # digits with country code, e.g. 91XXXXXXXXXX
    fee_amount = db.Column(db.Float, nullable=False, default=0)
    fee_cycle = db.Column(db.String(20), nullable=False, default="monthly")  # monthly / one-time
    join_date = db.Column(db.Date, default=date.today)
    active = db.Column(db.Boolean, default=True)

    attendances = db.relationship("Attendance", backref="student", cascade="all, delete-orphan")
    fees = db.relationship("Fee", backref="student", cascade="all, delete-orphan")

    def whatsapp_link(self):
        return f"+{self.whatsapp_number}" if not self.whatsapp_number.startswith("+") else self.whatsapp_number


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
