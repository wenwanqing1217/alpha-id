"""Test SQLite I/O with the same path the service uses"""
import os, sqlite3, sys

db_dir = os.path.join(os.path.expanduser("~"), ".alpha-id")
db_path = os.path.join(db_dir, "alpha_id.db")

print(f"DB path: {db_path}")
print(f"Exists: {os.path.exists(db_path)}")
print(f"Size: {os.path.getsize(db_path) if os.path.exists(db_path) else 'N/A'}")

# Test with WAL mode (same as service)
try:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    
    # Try a simple read
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"Tables: {tables}")
    
    # Try a simple write
    conn.execute("CREATE TABLE IF NOT EXISTS _io_test (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO _io_test (val) VALUES (?)", ("test",))
    conn.commit()
    rows = conn.execute("SELECT * FROM _io_test").fetchall()
    print(f"IO test: {rows}")
    
    # Cleanup
    conn.execute("DROP TABLE _io_test")
    conn.commit()
    conn.close()
    print("SUCCESS: Database read/write OK")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
