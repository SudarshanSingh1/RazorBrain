import re

with open("api/app.py", "r") as f:
    text = f.read()

import os
# We will inject the code right before app.add_middleware(CORSMiddleware...

new_cors_code = """
import os
cors_origins_env = os.environ.get("RAZORBRAIN_CORS_ORIGINS", "*")
allow_origins = [origin.strip() for origin in cors_origins_env.split(",")] if cors_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""

text = re.sub(r'app\.add_middleware\(\s*CORSMiddleware,.*?allow_headers=\["\*"\]\s*,\s*\)', new_cors_code.strip(), text, flags=re.DOTALL)

with open("api/app.py", "w") as f:
    f.write(text)
