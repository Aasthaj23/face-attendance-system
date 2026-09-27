import csv
import io


EXPORT_COLUMNS = ["Date", "Student", "Roll No", "Subject", "Time", "Status"]


def attendance_csv(records) -> io.BytesIO:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(EXPORT_COLUMNS)
    for record in records:
        writer.writerow([
            record.date.isoformat(),
            record.student.name,
            record.student.roll_no,
            record.subject.name,
            record.timestamp.strftime("%H:%M:%S"),
            record.status,
        ])
    buffer = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    buffer.seek(0)
    return buffer
