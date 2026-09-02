with open("tests/test_security.py", "r") as f:
    text = f.read()

text = text.replace("def generate_explanation", "def explain")

# Fix lifespan triggers in traceback test
traceback_test = """
def test_traceback_leak_prevention():
    # Force an unhandled exception in the endpoint
    with patch("api.routes.assess_transaction", side_effect=ValueError("Secret internal error")):
        with TestClient(app) as client:
            payload = {
                "transaction_id": "TX-1",
                "timestamp": "2023-01-01T12:00:00Z",
                "amount": 100.0,
                "currency": "USD",
                "customer_id": "C-001",
                "merchant_id": "M-001",
                "payment_method": "credit_card"
            }
            response = client.post("/transactions/assess", json=payload)
            assert response.status_code == 500
            # The internal message "Secret internal error" MUST NOT be returned!
            assert "Secret internal error" not in response.text
            assert "Internal Server Error" in response.text
"""
import re
text = re.sub(r'def test_traceback_leak_prevention\(\):.*?assert "Internal Server Error" in response\.text', traceback_test.strip(), text, flags=re.DOTALL)

with open("tests/test_security.py", "w") as f:
    f.write(text)
