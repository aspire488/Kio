import sqlite3, os
for f in ['kio_user_session.session', 'kio_live_session.session', 'kio_live_test_user.session']:
    if os.path.exists(f):
        try:
            conn = sqlite3.connect(f)
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            print(f'{f}: tables={tables}')
            for t in tables:
                count = conn.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0]
                print(f'  {t}: {count} rows')
            conn.close()
        except Exception as e:
            print(f'{f}: ERROR {e}')
