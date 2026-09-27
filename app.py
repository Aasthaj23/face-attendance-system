import os
import secrets
from datetime import datetime

from flask import Flask, jsonify, render_template
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import ATTENDANCE_THRESHOLD, SUBJECTS, validate_security_config
from models import Attendance, Student, Subject, User, db
from routes.attendance import attendance_bp
from routes.analytics import analytics_bp
from routes.auth import auth_bp
from routes.recognition import recognition_bp
from routes.students import students_bp
from services.face_service import known_names
from utils.logger import get_logger


logger = get_logger(__name__)


def create_app(config_overrides=None) -> Flask:
    application = Flask(__name__)
    application.config.from_object("config.Config")
    if config_overrides:
        application.config.update(config_overrides)
    validate_security_config(application.config)
    db.init_app(application)
    JWTManager(application)
    CORS(application)
    application.register_blueprint(auth_bp)
    application.register_blueprint(students_bp)
    application.register_blueprint(attendance_bp)
    application.register_blueprint(analytics_bp)
    application.register_blueprint(recognition_bp)

    @application.get("/")
    def login_page():
        return render_template("login.html")

    @application.get("/dashboard")
    def dashboard():
        return render_template("attendance.html")

    @application.get("/students")
    def students_page():
        return render_template("students.html")

    @application.get("/api/status")
    def api_status():
        today = datetime.now().strftime("%Y-%m-%d")
        return jsonify({
            "marked_today": Attendance.query.filter(Attendance.date == datetime.now().date()).count(),
            "known_faces": len(known_names),
            "total_students": Student.query.count(),
            "subjects": SUBJECTS,
            "threshold": ATTENDANCE_THRESHOLD,
        })

    with application.app_context():
        db.create_all()
        if User.query.count() == 0:
            admin_password = os.environ.get("ADMIN_PASSWORD")
            if not admin_password:
                admin_password = secrets.token_urlsafe(24)
                logger.warning("ADMIN_PASSWORD is unset; generated a random bootstrap password")
            bootstrap_user = User(
                username=os.environ.get("ADMIN_USERNAME", "admin"),
                role=os.environ.get("ADMIN_ROLE", "ADMIN").upper(),
            )
            bootstrap_user.set_role(bootstrap_user.role)
            bootstrap_user.set_password(admin_password)
            db.session.add(bootstrap_user)
            db.session.commit()
        db.session.execute(db.text("""
            DELETE FROM attendance
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM attendance
                GROUP BY student_id, subject_id, date
            )
        """))
        db.session.commit()
        db.session.execute(db.text("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            uq_attendance_student_subject_date
            ON attendance (student_id, subject_id, date)
        """))
        db.session.commit()
        for subject_name in SUBJECTS:
            if not Subject.query.filter_by(name=subject_name).first():
                db.session.add(Subject(name=subject_name))
        db.session.commit()
        for column_sql in (
            "ALTER TABLE attendance_record ADD COLUMN roll_no VARCHAR(50)",
            "ALTER TABLE attendance_record ADD COLUMN subject VARCHAR(100) DEFAULT 'General'",
        ):
            try:
                with db.engine.connect() as connection:
                    connection.execute(db.text(column_sql))
                    connection.commit()
            except Exception:
                pass
    return application


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)