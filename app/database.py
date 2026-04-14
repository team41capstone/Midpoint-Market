from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus

SERVER = r"localhost\SQLEXPRESS01"
DATABASE = "StockTradingSystem"
DRIVER = "ODBC Driver 18 for SQL Server"

params = quote_plus(
    f"DRIVER={{{DRIVER}}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"Trusted_Connection=yes;"
    f"TrustServerCertificate=yes;"
)

connection_string = f"mssql+pyodbc:///?odbc_connect={params}"

engine = create_engine(connection_string, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_db_connection():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DB_NAME()"))
        return result.fetchone()