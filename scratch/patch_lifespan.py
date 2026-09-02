import re

with open("api/lifespan.py", "r") as f:
    text = f.read()

# Add import os if not there
if "import os" not in text:
    text = text.replace("import asyncio", "import asyncio\nimport os")

# Replace self.db_path = "razorbrain_api.db"
search_str = 'self.db_path = "razorbrain_api.db"'
replace_str = 'self.db_path = os.environ.get("RAZORBRAIN_DB_PATH", "razorbrain_api.db")'

if search_str in text:
    text = text.replace(search_str, replace_str)

with open("api/lifespan.py", "w") as f:
    f.write(text)
