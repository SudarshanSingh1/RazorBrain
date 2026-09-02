with open("api/dashboard_routes.py", "r") as f:
    text = f.read()

# Fix the SELECT statement
text = text.replace(
    "t.merchant_id, t.payment_method, t.context_data",
    "t.merchant_id, t.context_data"
)

# Extract payment_method from context_data
search_str = """        # Context data is JSON
        if row.get("context_data"):
            row["context_data"] = json.loads(row["context_data"])"""

replace_str = """        # Context data is JSON
        if row.get("context_data"):
            row["context_data"] = json.loads(row["context_data"])
            row["payment_method"] = row["context_data"].get("payment_method")"""

if search_str in text:
    text = text.replace(search_str, replace_str)
else:
    print("Could not find the context_data block")

with open("api/dashboard_routes.py", "w") as f:
    f.write(text)
