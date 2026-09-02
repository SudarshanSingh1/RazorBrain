with open("api/schemas.py", "r") as f:
    text = f.read()

text = text.replace("    from pydantic import ConfigDict\n", "")
text = text.replace("from pydantic import BaseModel, Field, constr", "from pydantic import BaseModel, Field, constr, ConfigDict")

with open("api/schemas.py", "w") as f:
    f.write(text)
