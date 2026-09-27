import os
from datetime import datetime

from flask import Flask, jsonify, render_template
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import ATTENDANCE_THRESHOLD, SUBJECTS
from models import db
from models.attendance import AttendanceRecord
from models.student import load_students
from routes.attendance import attendance_bp
from routes.auth import auth_bp
from routes.recognition import recognition_bp
from routes.students import students_bp
from services.face_service import known_names


def create_app() -> Flask:
    application = Flask(__name__)
    application.config.from_object("config.Config")
    db.init_app(application)
    JWTManager(application)
    CORS(application)
    application.register_blueprint(auth_bp)
    application.register_blueprint(students_bp)
    application.register_blueprint(attendance_bp)
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
            "marked_today": AttendanceRecord.query.filter(AttendanceRecord.timestamp.startswith(today)).count(),
            "known_faces": len(known_names),
            "total_students": len(load_students()),
            "subjects": SUBJECTS,
            "threshold": ATTENDANCE_THRESHOLD,
        })

    with application.app_context():
        db.create_all()
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