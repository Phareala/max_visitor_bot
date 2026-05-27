import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visitor_passes.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        # Create users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                role TEXT DEFAULT 'initiator',
                consent_given INTEGER DEFAULT 0,
                consent_time TEXT,
                consent_version TEXT
            )
        """)
        
        # Create requests table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                initiator_id TEXT,
                visitor_name TEXT,
                visit_date TEXT,
                visit_time TEXT,
                visit_zone TEXT,
                visit_purpose TEXT,
                status TEXT DEFAULT 'draft',
                rejection_reason TEXT,
                admin_comment TEXT,
                clarification_question TEXT,
                clarification_answer TEXT,
                created_at TEXT
            )
        """)
        
        # Create audit_log table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER,
                event_type TEXT,
                event_time TEXT,
                performer_id TEXT,
                old_status TEXT,
                new_status TEXT,
                comment TEXT
            )
        """)
        
        # Create custom_fields table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_fields (
                field_id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_name TEXT,
                field_name TEXT,
                is_required INTEGER DEFAULT 1,
                description TEXT,
                created_at TEXT
            )
        """)
        
        # Create request_custom_fields table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_custom_fields (
                request_id INTEGER,
                field_name TEXT,
                field_value TEXT,
                PRIMARY KEY (request_id, field_name),
                FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE
            )
        """)
        conn.commit()

# --- User Management ---

def get_user(user_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()
        return dict(row) if row else None

def get_user_role(user_id, default_admin_ids, default_tech_admin_ids):
    user_id_str = str(user_id)
    # Check default IDs from configuration first
    if user_id_str in default_tech_admin_ids:
        return "tech_admin"
    if user_id_str in default_admin_ids:
        return "admin"
    
    # Otherwise check database
    user = get_user(user_id_str)
    if user:
        return user["role"]
    return "initiator"

def create_or_update_user(user_id, display_name, role="initiator"):
    user_id_str = str(user_id)
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO users (user_id, display_name, role)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name,
                role = CASE WHEN users.role != 'initiator' THEN users.role ELSE excluded.role END
        """, (user_id_str, display_name, role))
        conn.commit()

def give_consent(user_id, display_name, role="initiator", version="1.0"):
    user_id_str = str(user_id)
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO users (user_id, display_name, role, consent_given, consent_time, consent_version)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name,
                consent_given = 1,
                consent_time = excluded.consent_time,
                consent_version = excluded.consent_version
        """, (user_id_str, display_name, role, now, version))
        conn.commit()
    
    # Log consent acceptance in audit log (use request_id = 0 for user actions not linked to requests)
    log_audit_event(0, "consent_accepted", user_id_str, None, None, f"Consent version {version} accepted")

def delete_user_data(user_id):
    user_id_str = str(user_id)
    # Log audit event for data deletion BEFORE deleting
    log_audit_event(0, "user_data_deleted", user_id_str, None, None, "User requested complete data deletion")
    
    with get_db_connection() as conn:
        # Delete request custom fields first
        conn.execute("""
            DELETE FROM request_custom_fields
            WHERE request_id IN (SELECT request_id FROM requests WHERE initiator_id = ?)
        """, (user_id_str,))
        # Delete requests initiated by the user
        conn.execute("DELETE FROM requests WHERE initiator_id = ?", (user_id_str,))
        # Delete user record itself
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id_str,))
        conn.commit()

# --- Request Management ---

def create_request(initiator_id, visitor_name, visit_date, visit_time, visit_zone, visit_purpose):
    initiator_id_str = str(initiator_id)
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO requests (initiator_id, visitor_name, visit_date, visit_time, visit_zone, visit_purpose, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'draft', ?)
        """, (initiator_id_str, visitor_name, visit_date, visit_time, visit_zone, visit_purpose, now))
        request_id = cursor.lastrowid
        conn.commit()
    
    log_audit_event(request_id, "request_created", initiator_id_str, None, "draft")
    return request_id

def update_request_status(request_id, new_status, performer_id, comment=None, rejection_reason=None):
    performer_id_str = str(performer_id)
    req = get_request(request_id)
    if not req:
        return False
    
    old_status = req["status"]
    
    with get_db_connection() as conn:
        if new_status == "rejected":
            conn.execute("""
                UPDATE requests
                SET status = ?, rejection_reason = ?, admin_comment = ?
                WHERE request_id = ?
            """, (new_status, rejection_reason, comment, request_id))
        elif new_status == "approved":
            conn.execute("""
                UPDATE requests
                SET status = ?, admin_comment = ?
                WHERE request_id = ?
            """, (new_status, comment, request_id))
        else:
            conn.execute("""
                UPDATE requests
                SET status = ?
                WHERE request_id = ?
            """, (new_status, request_id))
        conn.commit()
    
    log_audit_event(request_id, "status_changed", performer_id_str, old_status, new_status, comment or rejection_reason)
    return True

def get_request(request_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
        return dict(row) if row else None

def get_user_requests(user_id):
    user_id_str = str(user_id)
    auto_expire_requests()
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM requests
            WHERE initiator_id = ?
            ORDER BY request_id DESC
        """, (user_id_str,)).fetchall()
        return [dict(r) for r in rows]

def get_admin_queue():
    auto_expire_requests()
    with get_db_connection() as conn:
        # Join with users to get initiator's display name
        rows = conn.execute("""
            SELECT r.*, u.display_name as initiator_name
            FROM requests r
            LEFT JOIN users u ON r.initiator_id = u.user_id
            WHERE r.status = 'review'
            ORDER BY r.request_id ASC
        """).fetchall()
        return [dict(r) for r in rows]

def set_clarification_question(request_id, question, performer_id):
    performer_id_str = str(performer_id)
    req = get_request(request_id)
    if not req:
        return False
    
    old_status = req["status"]
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE requests
            SET status = 'clarification', clarification_question = ?, clarification_answer = NULL
            WHERE request_id = ?
        """, (question, request_id))
        conn.commit()
    
    log_audit_event(request_id, "clarification_requested", performer_id_str, old_status, "clarification", question)
    return True

def submit_clarification_answer(request_id, answer, performer_id):
    performer_id_str = str(performer_id)
    req = get_request(request_id)
    if not req:
        return False
    
    old_status = req["status"]
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE requests
            SET status = 'review', clarification_answer = ?
            WHERE request_id = ?
        """, (answer, request_id))
        conn.commit()
    
    log_audit_event(request_id, "clarification_answered", performer_id_str, old_status, "review", answer)
    return True

# --- Audit Log & Technical Admin ---

def log_audit_event(request_id, event_type, performer_id, old_status, new_status, comment=None):
    performer_id_str = str(performer_id)
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO audit_log (request_id, event_type, event_time, performer_id, old_status, new_status, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (request_id, event_type, now, performer_id_str, old_status, new_status, comment))
        conn.commit()

def get_audit_logs(request_id=None):
    with get_db_connection() as conn:
        if request_id is not None:
            rows = conn.execute("""
                SELECT * FROM audit_log
                WHERE request_id = ?
                ORDER BY log_id ASC
            """, (request_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM audit_log
                ORDER BY log_id DESC
                LIMIT 100
            """).fetchall()
        return [dict(r) for r in rows]

def get_system_stats():
    auto_expire_requests()
    with get_db_connection() as conn:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        request_count = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        
        status_rows = conn.execute("SELECT status, COUNT(*) FROM requests GROUP BY status").fetchall()
        status_stats = {r[0]: r[1] for r in status_rows}
        
        consent_count = conn.execute("SELECT COUNT(*) FROM users WHERE consent_given = 1").fetchone()[0]
        
        return {
            "total_users": user_count,
            "total_requests": request_count,
            "consented_users": consent_count,
            "status_stats": status_stats
        }

# --- Custom Fields Helper Functions ---

def add_custom_field(zone_name, field_name, is_required, description):
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO custom_fields (zone_name, field_name, is_required, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (zone_name, field_name, int(is_required), description, now))
        conn.commit()

def delete_custom_field(field_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM custom_fields WHERE field_id = ?", (field_id,))
        conn.commit()

def get_custom_field(field_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM custom_fields WHERE field_id = ?", (field_id,)).fetchone()
        return dict(row) if row else None

def get_custom_field_by_name(field_name, zone_name):
    with get_db_connection() as conn:
        row = conn.execute("""
            SELECT * FROM custom_fields
            WHERE field_name = ? AND (zone_name = ? OR zone_name = 'Все корпуса')
            LIMIT 1
        """, (field_name, zone_name)).fetchone()
        return dict(row) if row else None

def get_custom_fields(zone_name):
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM custom_fields
            WHERE zone_name = ? OR zone_name = 'Все корпуса'
            ORDER BY field_id ASC
        """, (zone_name,)).fetchall()
        return [dict(r) for r in rows]

def get_custom_fields_by_zone_exact(zone_name):
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM custom_fields
            WHERE zone_name = ?
            ORDER BY field_id ASC
        """, (zone_name,)).fetchall()
        return [dict(r) for r in rows]

def save_request_custom_field_value(request_id, field_name, field_value):
    with get_db_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO request_custom_fields (request_id, field_name, field_value)
            VALUES (?, ?, ?)
        """, (request_id, field_name, field_value))
        conn.commit()

def get_request_custom_fields(request_id):
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT field_name, field_value FROM request_custom_fields
            WHERE request_id = ?
        """, (request_id,)).fetchall()
        return {r["field_name"]: r["field_value"] for r in rows}

# --- Auto Expiration & Period-based Statistics ---

def auto_expire_requests():
    now = datetime.now()
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT request_id, visit_date, visit_time, status
            FROM requests
            WHERE status IN ('draft', 'review', 'clarification')
        """).fetchall()
        
        expired_ids = []
        for row in rows:
            try:
                visit_dt = datetime.strptime(f"{row['visit_date']} {row['visit_time']}", "%d.%m.%Y %H:%M")
                if visit_dt < now:
                    expired_ids.append((row['request_id'], row['status']))
            except Exception:
                pass
        
        if expired_ids:
            for req_id, old_status in expired_ids:
                conn.execute("""
                    UPDATE requests
                    SET status = 'expired'
                    WHERE request_id = ?
                """, (req_id,))
                
                conn.execute("""
                    INSERT INTO audit_log (request_id, event_type, event_time, performer_id, old_status, new_status, comment)
                    VALUES (?, 'status_changed', ?, 'system', ?, 'expired', 'Автоматическое закрытие по истечению срока действия')
                """, (req_id, now.isoformat(), old_status))
            conn.commit()

def get_period_stats(days=None):
    with get_db_connection() as conn:
        if days is not None:
            from datetime import timedelta
            start_date = (datetime.now() - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
            start_iso = start_date.isoformat()
            query_filter = "WHERE created_at >= ?"
            params = (start_iso,)
        else:
            query_filter = ""
            params = ()
            
        if days is not None:
            user_count = conn.execute("SELECT COUNT(*) FROM users WHERE consent_time >= ?", params).fetchone()[0]
        else:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            
        req_count = conn.execute(f"SELECT COUNT(*) FROM requests {query_filter}", params).fetchone()[0]
        
        status_rows = conn.execute(f"""
            SELECT status, COUNT(*) 
            FROM requests 
            {query_filter}
            GROUP BY status
        """, params).fetchall()
        status_stats = {r[0]: r[1] for r in status_rows}
        
        campus_rows = conn.execute(f"""
            SELECT visit_zone, COUNT(*) 
            FROM requests 
            {query_filter}
            GROUP BY visit_zone
            ORDER BY COUNT(*) DESC
        """, params).fetchall()
        campus_stats = {r[0]: r[1] for r in campus_rows}
        
        return {
            "total_users": user_count,
            "total_requests": req_count,
            "status_stats": status_stats,
            "campus_stats": campus_stats
        }

def get_all_requests_for_export():
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT r.*, u.display_name as initiator_name
            FROM requests r
            LEFT JOIN users u ON r.initiator_id = u.user_id
            ORDER BY r.request_id ASC
        """).fetchall()
        
        requests_list = []
        for r in rows:
            req_dict = dict(r)
            req_dict["custom_fields"] = get_request_custom_fields(req_dict["request_id"])
            requests_list.append(req_dict)
        return requests_list
