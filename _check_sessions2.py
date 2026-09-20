import sqlite3
for f in ['kio_user_session.session', 'kio_live_session.session', 'kio_live_test_user.session']:
    conn = sqlite3.connect(f)
    row = conn.execute("SELECT * FROM sessions").fetchone()
    if row:
        print(f'{f}: session row cols={len(row)}, has_dc={row[1] if len(row) > 1 else "N/A"}')
    conn.close()
