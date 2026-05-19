import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

def _conn_str() -> str:
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.environ['DB_SERVER']};"
        f"DATABASE={os.environ['DB_NAME']};"
        f"UID={os.environ['DB_USER']};"
        f"PWD={os.environ['DB_PASSWORD']};"
        "TrustServerCertificate=yes;"
        "ConnectTimeout=10;"
    )

def query(sql: str, params=None) -> list[dict]:
    conn = pyodbc.connect(_conn_str())
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()

def execute(sql: str, params=None) -> None:
    conn = pyodbc.connect(_conn_str())
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        conn.commit()
    finally:
        conn.close()

def execute_scalar(sql: str, params=None):
    """Ejecuta y retorna el primer campo de la primera fila."""
    conn = pyodbc.connect(_conn_str())
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        conn.commit()
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def migrate():
    """Crea tablas OPR si no existen. Llamar al inicio de la app."""
    ddl = """
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'opr' AND TABLE_NAME = 'contratos_enviados'
    )
    BEGIN
        CREATE TABLE opr.contratos_enviados (
            Id           INT IDENTITY(1,1) PRIMARY KEY,
            IdReserva    INT          NOT NULL,
            EmailDestino VARCHAR(255) NOT NULL,
            FechaEnvio   DATETIME     NOT NULL DEFAULT GETDATE(),
            NombreArchivo VARCHAR(500)
        )
    END
    """
    execute(ddl)
