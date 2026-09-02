import asyncio
import time
import uuid
import httpx
from api.app import app
from api.lifespan import lifespan

async def submit_events(client, num_events):
    start = time.perf_counter()
    tasks = []
    
    async def fire(i):
        payload = {
            "transaction_id": f"TX-EV-{i}",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 100.0,
            "currency": "USD",
            "customer_id": "C-001",
            "merchant_id": "M-001",
            "payment_method": "credit_card"
        }
        resp = await client.post("/transactions/events", json=payload)
        return resp.status_code
        
    tasks = [fire(i) for i in range(num_events)]
    results = await asyncio.gather(*tasks)
    return results, time.perf_counter() - start

async def main():
    import sqlite3
    
    # Reset DB
    import os
    if os.path.exists("razorbrain_api.db"):
        os.remove("razorbrain_api.db")
        
    transport = httpx.ASGITransport(app=app)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            
            print("Blasting 1000 events into the queue...")
            res, dur = await submit_events(client, 1000)
            print(f"Ingestion took {dur:.2f}s. Waiting for queue to drain...")
            
            # Now wait for the queue to drain and measure time
            from api.lifespan import app_state
            
            start_drain = time.perf_counter()
            while not app_state.broker.queue.empty():
                await asyncio.sleep(0.5)
            drain_time = time.perf_counter() - start_drain
            
            print(f"Queue drained in {drain_time:.2f}s.")
            
            # Check DB
            with sqlite3.connect(app_state.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM processed_events")
                processed = c.fetchone()[0]
                print(f"Processed events in DB: {processed}")
                
            print(f"Processing RPS: {processed / drain_time:.2f} events/sec")

if __name__ == "__main__":
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("api").setLevel(logging.WARNING)
    asyncio.run(main())
