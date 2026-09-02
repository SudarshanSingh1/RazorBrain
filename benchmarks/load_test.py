import asyncio
import httpx
import pandas as pd
import time
import argparse
import sys
import numpy as np

def prepare_payloads(limit=1000):
    df = pd.read_parquet("scratch/load_test_100k.parquet")
    if limit:
        df = df.head(limit)
    
    # Convert types to python native
    df = df.replace({np.nan: None})
    records = df.to_dict('records')
    
    payloads = []
    for r in records:
        payload = {
            "transaction_id": str(r.get("transaction_id", f"TX-{time.time_ns()}")),
            "timestamp": str(r.get("timestamp", "2023-01-01T12:00:00Z")),
            "amount": float(r.get("amount", 0.0)),
            "currency": "USD",
            "customer_id": str(r.get("customer_id", "C-000")),
            "merchant_id": str(r.get("merchant_id", "M-000")),
            "payment_method": str(r.get("payment_method", "credit_card"))
        }
        # Copy optional fields if they exist
        optional = [
            "previous_transaction_count", "previous_fraud_count", "avg_customer_amount", 
            "amount_deviation", "is_new_customer", "merchant_fraud_rate", 
            "is_new_merchant", "txns_last_5min", "txns_last_1h", "txns_last_24h"
        ]
        for opt in optional:
            if r.get(opt) is not None:
                payload[opt] = float(r[opt]) if isinstance(r[opt], (int, float, np.number)) else r[opt]
        payloads.append(payload)
    return payloads

async def run_worker(client, semaphore, url, payloads, results):
    async def fetch(payload):
        async with semaphore:
            start = time.perf_counter()
            try:
                resp = await client.post(url, json=payload, timeout=30.0)
                end = time.perf_counter()
                results.append({"status": resp.status_code, "time": end - start})
            except Exception as e:
                end = time.perf_counter()
                results.append({"status": f"ERROR: {type(e).__name__}: {e}", "time": end - start, "error": str(e)})
    
    tasks = [fetch(p) for p in payloads]
    await asyncio.gather(*tasks)

async def main(url, concurrency, count):
    print(f"Preparing {count} payloads...")
    payloads = prepare_payloads(limit=count)
    print("Done preparing.")

    results = []
    semaphore = asyncio.Semaphore(concurrency)
    
    transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
    async with httpx.AsyncClient(transport=transport, timeout=30.0) as client:
        start_time = time.perf_counter()
        await run_worker(client, semaphore, url, payloads, results)
        end_time = time.perf_counter()

    elapsed = end_time - start_time
    successes = [r for r in results if r["status"] in (201, 202)]
    errors = [r for r in results if r["status"] not in (201, 202)]
    
    times = [r["time"] for r in results]
    times.sort()
    
    p50 = times[int(len(times)*0.5)] if times else 0
    p95 = times[int(len(times)*0.95)] if times else 0
    p99 = times[int(len(times)*0.99)] if times else 0
    max_t = times[-1] if times else 0
    
    rps = len(results) / elapsed if elapsed > 0 else 0
    
    print("\n--- RESULTS ---")
    print(f"Total Completed: {len(results)}")
    print(f"Total Success:   {len(successes)}")
    print(f"Total Failed:    {len(errors)}")
    if errors:
        from collections import Counter
        err_counts = Counter(str(r["status"]) for r in errors)
        print(f"Error breakdown: {dict(err_counts)}")
    print(f"Elapsed Time:    {elapsed:.2f}s")
    print(f"RPS:             {rps:.2f} req/s")
    print(f"P50 Latency:     {p50*1000:.2f} ms")
    print(f"P95 Latency:     {p95*1000:.2f} ms")
    print(f"P99 Latency:     {p99*1000:.2f} ms")
    print(f"Max Latency:     {max_t*1000:.2f} ms")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/transactions/assess")
    parser.add_argument("--c", type=int, default=10)
    parser.add_argument("--n", type=int, default=1000)
    args = parser.parse_args()
    
    asyncio.run(main(args.url, args.c, args.n))
