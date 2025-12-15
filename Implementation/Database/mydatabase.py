from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text
from sqlalchemy.orm import sessionmaker , declarative_base



DATABASE_URL = 'postgresql+psycopg2://postgres:Scott3988@localhost:5432/mydatabase'

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

class user_request(Base):
     __tablename__ = 'users_requests'
     id =Column(Integer, primary_key=True, index=True)
     #user_id =Column(String, index=True)
     request_text =Column(String, index=True)
     created_at =Column(String, index=True)
     print("User class initialized")




if __name__ == "__main__":
    test_connection()
    Base.metadata.create_all(bind=engine)
    Base.metadata.delete(user.__table__, checkfirst=True)
