import asyncio
import httpx
import uuid
import collections
from api.app import app
from api.lifespan import lifespan

async def test_sequential():
    print("--- SEQUENTIAL ---")
    transport = httpx.ASGITransport(app=app)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            payload = {
                "transaction_id": "TX-SEQ-1",
                "timestamp": "2023-01-01T12:00:00Z",
                "amount": 100.0,
                "currency": "USD",
                "customer_id": "C-001",
                "merchant_id": "M-001",
                "payment_method": "credit_card",
                "assessment_id": str(uuid.uuid4())
            }
            resp1 = await client.post("/transactions/events", json=payload)
            print("Request 1:", resp1.status_code)
            resp2 = await client.post("/transactions/events", json=payload)
            print("Request 2:", resp2.status_code)
            
            # Wait for queue drain
            from api.lifespan import app_state
            while not app_state.broker.queue.empty():
                await asyncio.sleep(0.1)
                
            import sqlite3
            with sqlite3.connect(app_state.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT status, COUNT(*) FROM processed_events GROUP BY status")
                print("Event statuses in DB:", c.fetchall())

async def test_concurrent(concurrency):
    print(f"--- CONCURRENT {concurrency} ---")
    import os
    if os.path.exists("razorbrain_api.db"):
        os.remove("razorbrain_api.db")
        
    transport = httpx.ASGITransport(app=app)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            payload = {
                "transaction_id": f"TX-CONC-{concurrency}",
                "timestamp": "2023-01-01T12:00:00Z",
                "amount": 100.0,
                "currency": "USD",
                "customer_id": "C-001",
                "merchant_id": "M-001",
                "payment_method": "credit_card",
                "assessment_id": str(uuid.uuid4())
            }
            
            tasks = [client.post("/transactions/events", json=payload) for _ in range(concurrency)]
            results = await asyncio.gather(*tasks)
            
            status_codes = [r.status_code for r in results]
            print(f"Ingestion Statuses: {dict(collections.Counter(status_codes))}")
            
            # Wait for queue drain
            from api.lifespan import app_state
            while not app_state.broker.queue.empty():
                await asyncio.sleep(0.1)
                
            import sqlite3
            with sqlite3.connect(app_state.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT status, COUNT(*) FROM processed_events GROUP BY status")
                print("Event statuses in DB:", c.fetchall())
                
                c.execute("SELECT COUNT(*) FROM risk_assessments")
                print("Assessments in DB:", c.fetchone()[0])

if __name__ == "__main__":
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("api").setLevel(logging.WARNING)
    asyncio.run(test_sequential())
    asyncio.run(test_concurrent(10))
    asyncio.run(test_concurrent(50))
