from sqlalchemy import create_engine, text

DATABASE_URL = (
    "mssql+pyodbc://OBSCURJ\\SQLEXPRESS01/MidpointMarkets?"
    "driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
)

engine = create_engine(DATABASE_URL)

def test_db_connection():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DB_NAME()"))
        return result.fetchone()