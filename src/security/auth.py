"""
Authentication and Password Management for MediNexus AI.
Supports password hashing (bcrypt / PBKDF2), persistent user registration in DuckDB,
and role-based authentication across all 7 personas.
"""

import os
import hashlib
import binascii
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from config.settings import DEMO_USERS, DEMO_PASSWORD_DEFAULT
from src.utils.database import execute_query, query_df, table_exists

try:
    import bcrypt

    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False


def hash_password(password: str) -> str:
    """Hash a password using bcrypt (or PBKDF2 fallback with salt)."""
    if BCRYPT_AVAILABLE:
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")
    else:
        salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return f"pbkdf2:{binascii.hexlify(salt).decode('ascii')}:{binascii.hexlify(key).decode('ascii')}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plain password against a stored hash."""
    if not hashed or not password:
        return False
    if hashed.startswith("pbkdf2:"):
        try:
            _, salt_hex, key_hex = hashed.split(":")
            salt = binascii.unhexlify(salt_hex)
            expected_key = binascii.unhexlify(key_hex)
            computed_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
            return computed_key == expected_key
        except Exception:
            return False
    elif BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False
    else:
        return False


# In-memory user store with hashed passwords initialized on first load
_USER_STORE: Dict[str, Dict[str, Any]] = {}


def init_users_table():
    """Ensure the DuckDB persistent users table exists."""
    try:
        execute_query("""
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR PRIMARY KEY,
                name VARCHAR,
                email VARCHAR,
                role VARCHAR,
                department VARCHAR,
                password_hash VARCHAR,
                created_at TIMESTAMP
            )
        """)
    except Exception:
        pass


def get_user_store() -> Dict[str, Dict[str, Any]]:
    """Retrieve initialized user store with hashed credentials and persistent database records."""
    global _USER_STORE
    if not _USER_STORE:
        init_users_table()
        # 1. Load built-in demo users
        for username, user_info in DEMO_USERS.items():
            _USER_STORE[username.lower()] = {
                "username": username.lower(),
                "name": user_info["name"],
                "email": user_info["email"],
                "role": user_info["role"],
                "department": user_info["department"],
                "password_hash": hash_password(user_info.get("plain_pwd", DEMO_PASSWORD_DEFAULT)),
            }

        # 2. Load registered users from DuckDB if available
        try:
            if table_exists("users"):
                df_db_users = query_df("SELECT * FROM users")
                for _, row in df_db_users.iterrows():
                    u_key = str(row["username"]).strip().lower()
                    _USER_STORE[u_key] = {
                        "username": u_key,
                        "name": str(row["name"]),
                        "email": str(row["email"]),
                        "role": str(row["role"]),
                        "department": str(row["department"]),
                        "password_hash": str(row["password_hash"]),
                    }
        except Exception:
            pass

    return _USER_STORE


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate username and password against the secure user store."""
    if not username or not password:
        return None
    users = get_user_store()
    user = users.get(username.strip().lower())
    if not user:
        return None
    if verify_password(password, user["password_hash"]):
        return {
            "username": user["username"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "department": user["department"],
        }
    return None


def register_user(
    username: str,
    name: str,
    email: str,
    role: str,
    department: str,
    password: str,
) -> Tuple[bool, str]:
    """
    Register a new user account for any persona and persist to DuckDB database.
    Returns (success: bool, message: str).
    """
    clean_username = username.strip().lower()
    clean_name = name.strip()
    clean_email = email.strip()
    clean_role = role.strip()
    clean_dept = department.strip()

    # Validation
    if len(clean_username) < 3:
        return False, "Username must be at least 3 characters long."
    if not clean_username.replace("_", "").isalnum():
        return False, "Username can only contain letters, numbers, and underscores."
    if len(clean_name) < 2:
        return False, "Please enter a valid full name."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if "@" not in clean_email or "." not in clean_email:
        return False, "Please provide a valid email address."

    users = get_user_store()
    if clean_username in users:
        return False, f"Username '{clean_username}' is already taken. Please choose another username."

    # Hash password
    pwd_hash = hash_password(password)
    now = datetime.now()

    # Persist in DuckDB
    try:
        init_users_table()
        execute_query(
            """
            INSERT INTO users (username, name, email, role, department, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [clean_username, clean_name, clean_email, clean_role, clean_dept, pwd_hash, now],
        )
    except Exception as e:
        # If DB error, still allow in-memory storage with warning
        pass

    # Update in-memory store
    users[clean_username] = {
        "username": clean_username,
        "name": clean_name,
        "email": clean_email,
        "role": clean_role,
        "department": clean_dept,
        "password_hash": pwd_hash,
    }

    return True, f"Account successfully created for {clean_name} ({clean_role})!"
