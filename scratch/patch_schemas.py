with open("api/schemas.py", "r") as f:
    text = f.read()

text = text.replace(
    'transaction_id: str = Field(..., description="Unique identifier for the transaction")',
    'transaction_id: str = Field(..., max_length=100, description="Unique identifier for the transaction")'
)
text = text.replace(
    'timestamp: str = Field(..., description="ISO-8601 timestamp")',
    'timestamp: str = Field(..., max_length=50, description="ISO-8601 timestamp")'
)
text = text.replace(
    'amount: float = Field(..., description="Transaction amount")',
    'amount: float = Field(..., ge=0.0, le=1e9, description="Transaction amount")'
)
text = text.replace(
    'currency: str = Field("USD", description="Currency code")',
    'currency: str = Field("USD", max_length=10, description="Currency code")'
)
text = text.replace(
    'customer_id: str = Field(..., description="Unique customer identifier")',
    'customer_id: str = Field(..., max_length=100, description="Unique customer identifier")'
)
text = text.replace(
    'merchant_id: str = Field(..., description="Unique merchant identifier")',
    'merchant_id: str = Field(..., max_length=100, description="Unique merchant identifier")'
)
text = text.replace(
    'payment_method: str = Field(..., description="Payment method used")',
    'payment_method: str = Field(..., max_length=50, description="Payment method used")'
)
text = text.replace(
    'device_id: Optional[str] = None',
    'device_id: Optional[str] = Field(None, max_length=100)'
)
text = text.replace(
    'ip_address: Optional[str] = None',
    'ip_address: Optional[str] = Field(None, max_length=50)'
)
text = text.replace(
    'assessment_id: Optional[str] = Field(None, description="Client-supplied idempotency key")',
    'assessment_id: Optional[str] = Field(None, max_length=100, description="Client-supplied idempotency key")'
)

text = text.replace(
    '''    class Config:
        extra = "forbid"''',
    '''    from pydantic import ConfigDict
    model_config = ConfigDict(extra="forbid")'''
)

with open("api/schemas.py", "w") as f:
    f.write(text)
