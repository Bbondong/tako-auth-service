"""Applique les migrations 005 (user.active) et 006 (favorite_locations) sur la base de .env puis les vérifie."""
from pathlib import Path

from src.data import get_connection

MIGRATIONS = Path(__file__).parent / 'migrations'
FILES = ('005_user_active.sql', '006_favorite_locations.sql')


def main():
    statements = [s.strip() for name in FILES for s in ''.join(
        line for line in (MIGRATIONS / name).read_text().splitlines(True)
        if not line.lstrip().startswith('--')
    ).split(';') if s.strip()]
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
            conn.commit()
            cursor.execute("SHOW COLUMNS FROM user LIKE 'active'")
            column = cursor.fetchone()
            assert column, "La colonne user.active est absente"
            cursor.execute("SHOW COLUMNS FROM favorite_locations")
            assert {c['Field'] for c in cursor.fetchall()} >= {
                'id', 'user_id', 'title', 'address', 'latitude', 'longitude', 'created_at'}
            cursor.execute('SELECT COUNT(*) AS total, SUM(active=1) AS actifs FROM user')
            counts = cursor.fetchone()
    finally:
        conn.close()
    print('Migration OK:', column['Type'], 'défaut', column['Default'])
    print('favorite_locations OK')
    print('Comptes:', counts['total'], '- actifs:', counts['actifs'])


def test_migration():
    main()


if __name__ == '__main__':
    main()
