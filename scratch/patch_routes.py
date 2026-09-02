import re

# PATCH api/routes.py
with open("api/routes.py", "r") as f:
    text = f.read()

if "Depends(get_api_key)" not in text:
    text = text.replace("from fastapi import APIRouter, Request, HTTPException, status", 
                        "from fastapi import APIRouter, Request, HTTPException, status, Depends\nfrom api.security import get_api_key")
    
    text = text.replace("async def assess(txn_request: TransactionRequest, request: Request):",
                        "async def assess(txn_request: TransactionRequest, request: Request, api_key: str = Depends(get_api_key)):")
    
    text = text.replace("async def submit_transaction_event(txn_request: TransactionRequest, request: Request):",
                        "async def submit_transaction_event(txn_request: TransactionRequest, request: Request, api_key: str = Depends(get_api_key)):")

with open("api/routes.py", "w") as f:
    f.write(text)

# PATCH api/dashboard_routes.py
with open("api/dashboard_routes.py", "r") as f:
    dtext = f.read()

if "Depends(get_api_key)" not in dtext:
    dtext = dtext.replace("from fastapi import APIRouter, HTTPException, Query",
                          "from fastapi import APIRouter, HTTPException, Query, Depends\nfrom api.security import get_api_key")
    
    # We can inject it using router dependencies for the whole router!
    dtext = dtext.replace("router = APIRouter(prefix=\"/dashboard\")",
                          "router = APIRouter(prefix=\"/dashboard\", dependencies=[Depends(get_api_key)])")

with open("api/dashboard_routes.py", "w") as f:
    f.write(dtext)
