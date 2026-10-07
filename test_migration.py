"""Applique migrations/005_user_active.sql sur la base de .env puis vérifie la colonne user.active."""
from pathlib import Path

from src.data import get_connection

SQL = Path(__file__).parent / 'migrations' / '005_user_active.sql'


def main():
    statements = [s.strip() for s in ''.join(
        line for line in SQL.read_text().splitlines(True) if not line.lstrip().startswith('--')
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
            cursor.execute('SELECT COUNT(*) AS total, SUM(active=1) AS actifs FROM user')
            counts = cursor.fetchone()
    finally:
        conn.close()
    print('Migration OK:', column['Type'], 'défaut', column['Default'])
    print('Comptes:', counts['total'], '- actifs:', counts['actifs'])


def test_migration():
    main()


if __name__ == '__main__':
    main()
