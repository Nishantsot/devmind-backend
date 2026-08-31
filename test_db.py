from sqlalchemy import text
from database import engine


try:
    with engine.connect() as connection:

        result = connection.execute(
            text("SELECT 1")
        )

        print("Result:", result.scalar())

    print("PostgreSQL connected successfully!")

except Exception as e:

    print("Database connection failed:")
    print(e)