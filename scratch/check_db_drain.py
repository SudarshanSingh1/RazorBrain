from database.connection import get_session
from sqlalchemy import text
from api.lifespan import app_state

with get_session(app_state.db_path) as session:
    res = session.execute(text("SELECT COUNT(*) FROM assessments")).scalar()
    print("Assessments in DB:", res)
