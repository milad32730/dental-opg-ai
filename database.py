import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "cases.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS cases (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        patient_id   TEXT,
        dentist_name TEXT,
        clinic_name  TEXT,
        date         TEXT,
        image_path   TEXT,
        analysis     TEXT,
        report_path  TEXT,
        notes        TEXT,
        created_at   TEXT
    )''')
    conn.commit()
    conn.close()


def save_case(patient_name, patient_id, dentist_name, clinic_name,
              image_path, analysis, report_path="", notes=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''INSERT INTO cases
           (patient_name, patient_id, dentist_name, clinic_name, date,
            image_path, analysis, report_path, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (patient_name, patient_id, dentist_name, clinic_name,
         datetime.now().strftime("%Y-%m-%d %H:%M"),
         image_path, analysis, report_path, notes,
         datetime.now().isoformat())
    )
    case_id = c.lastrowid
    conn.commit()
    conn.close()
    return case_id


def get_all_cases():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM cases ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows


def get_case(case_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM cases WHERE id = ?', (case_id,))
    row = c.fetchone()
    conn.close()
    return row


def delete_case(case_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM cases WHERE id = ?', (case_id,))
    conn.commit()
    conn.close()


def search_cases(query):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''SELECT * FROM cases
           WHERE patient_name LIKE ? OR patient_id LIKE ? OR dentist_name LIKE ?
           ORDER BY created_at DESC''',
        (f'%{query}%', f'%{query}%', f'%{query}%')
    )
    rows = c.fetchall()
    conn.close()
    return rows
