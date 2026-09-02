with open("scratch/measure_event_throughput.py", "r") as f:
    text = f.read()

text = text.replace('''        payload = {
            "metadata": {
                "event_id": str(uuid.uuid4()),
                "event_type": "transaction.created",
                "correlation_id": "corr-1"
            },
            "payload": {
                "transaction_id": f"TX-EV-{i}",
                "timestamp": "2023-01-01T12:00:00Z",
                "amount": 100.0,
                "currency": "USD",
                "customer_id": "C-001",
                "merchant_id": "M-001",
                "payment_method": "credit_card"
            }
        }''', '''        payload = {
            "transaction_id": f"TX-EV-{i}",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 100.0,
            "currency": "USD",
            "customer_id": "C-001",
            "merchant_id": "M-001",
            "payment_method": "credit_card"
        }''')

with open("scratch/measure_event_throughput.py", "w") as f:
    f.write(text)
