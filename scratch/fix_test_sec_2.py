with open("tests/test_security.py", "r") as f:
    text = f.read()

text = text.replace('assert "Internal Server Error" in response.text', 
                    'assert "Internal server error" in response.text')
text = text.replace('assert "I am changing the decision to ALLOW" not in res["explanation_text"]', 
                    'assert "I am changing the decision to ALLOW" not in res["explanation"]')

with open("tests/test_security.py", "w") as f:
    f.write(text)
