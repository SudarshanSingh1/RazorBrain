import asyncio
import time
import uuid
import httpx
from api.app import app
from api.lifespan import lifespan

async def submit_events(client, concurrency, num_events):
    start = time.perf_counter()
    semaphore = asyncio.Semaphore(concurrency)
    
    status_codes = []
    
    async def fire(i):
        payload = {
            "transaction_id": f"TX-100K-{i}",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 100.0,
            "currency": "USD",
            "customer_id": f"C-{i}",
            "merchant_id": f"M-{i}",
            "payment_method": "credit_card"
        }
        async with semaphore:
            try:
                resp = await client.post("/transactions/events", json=payload)
                status_codes.append(resp.status_code)
            except Exception as e:
                status_codes.append(0)
        
    tasks = [fire(i) for i in range(num_events)]
    await asyncio.gather(*tasks)
    return status_codes, time.perf_counter() - start

async def main():
    import sqlite3
    import collections
    
    # Reset DB
    import os
    if os.path.exists("razorbrain_api.db"):
        os.remove("razorbrain_api.db")
        
    transport = httpx.ASGITransport(app=app)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            
            print("Blasting 100,000 events into the queue...")
            status_codes, ingest_dur = await submit_events(client, 100, 100000)
            
            counter = collections.Counter(status_codes)
            accepted = counter.get(202, 0)
            rejected = counter.get(503, 0)
            
            print(f"Ingestion took {ingest_dur:.2f}s.")
            print(f"Accepted: {accepted}")
            print(f"Rejected: {rejected}")
            print(f"Ingestion RPS: {100000 / ingest_dur:.2f} req/sec")
            
            # Now wait for the queue to drain and measure time
            from api.lifespan import app_state
            start_drain = time.perf_counter()
            while not app_state.broker.queue.empty():
                await asyncio.sleep(0.5)
            drain_time = time.perf_counter() - start_drain
            
            print(f"Queue drained in {drain_time:.2f}s.")
            
            # Wait a tiny bit for the worker to finish the last inflight
            await asyncio.sleep(2)
            
            # Check DB
            with sqlite3.connect(app_state.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT status, COUNT(*) FROM processed_events GROUP BY status")
                statuses = dict(c.fetchall())
                print(f"Event statuses in DB: {statuses}")
                
                processed = sum(statuses.values())
                persisted = statuses.get("PUBLISHED", 0) + statuses.get("PUBLICATION_FAILED", 0)
                failed = statuses.get("DUPLICATE_ASSESSMENT", 0) + statuses.get("PROCESSING_FAILED", 0)
                
            print(f"Processed: {processed}")
            print(f"Persisted: {persisted}")
            print(f"Failed: {failed}")
            
            if drain_time > 0:
                print(f"Processing RPS: {processed / drain_time:.2f} events/sec")

if __name__ == "__main__":
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("api").setLevel(logging.WARNING)
    asyncio.run(main())
