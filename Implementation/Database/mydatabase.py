import os

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text
from sqlalchemy.orm import sessionmaker , declarative_base
from dotenv import load_dotenv

load_dotenv()

# Never hardcode credentials. Provide DATABASE_URL via environment / .env file.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Define it in your environment or a .env file, "
        "e.g. postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME"
    )

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db=SessionLocal()

Base = declarative_base()
metadata = MetaData()

def test_connection():
    try:
        
            print("Trying to connect to the database...")
            engine = create_engine(DATABASE_URL, echo=False)
            with engine.connect() as connection:
                result = connection.execute(text("SELECT 1"))
                print("Test query result:", result.scalar())
    except Exception as e:
        print(f"An error occurred: {e}")

class UserRequest(Base):
    __tablename__ = 'users_requests'
    id = Column(Integer, primary_key=True, index=True)
    request_text = Column(String, index=True)
    created_at = Column(String, index=True)


if __name__ == "__main__":
    test_connection()
    Base.metadata.create_all(bind=engine)
