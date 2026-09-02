with open("README.md", "r") as f:
    text = f.read()

# Add the note under Database / Audit Trail
search_str = "## Database / Audit Trail\n\nRazorBrain implements an **append-only audit persistence** layer via SQLite."
replace_str = search_str + "\n\n*(Note: Current deployment uses SQLite. PostgreSQL is reserved as a future production database option and is not currently enabled.)*"

if search_str in text:
    text = text.replace(search_str, replace_str)
else:
    # try finding just Database / Audit Trail
    search_str2 = "## Database / Audit Trail"
    replace_str2 = search_str2 + "\n\n*(Note: Current deployment uses SQLite. PostgreSQL is reserved as a future production database option and is not currently enabled.)*"
    text = text.replace(search_str2, replace_str2)

with open("README.md", "w") as f:
    f.write(text)
