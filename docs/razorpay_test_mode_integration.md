# Razorpay Test Mode Integration

## 1. Architectural Overview
RazorBrain integrates with Razorpay via standard REST APIs and Webhooks to assess transactions for fraud risk. Currently, this integration operates exclusively in **Test Mode** using `rzp_test_*` credentials.

## 2. Event Idempotency & Concurrency
Webhooks from Razorpay can occasionally be duplicated or delayed. 
- The system enforces durable database-level idempotency based on the `x-razorpay-event-id` header.
- A `processed_events` SQLite table tracks every webhook.
- The `reserve_event()` transaction ensures a webhook event ID is locked atomically before any ML scoring or DB mutation occurs, preventing race conditions if duplicate webhooks arrive concurrently.

## 3. Webhook Signature Verification
- Webhooks are cryptographically authenticated using `x-razorpay-signature`.
- The signature is verified using `hmac.compare_digest` with HMAC-SHA256, validating the raw request body bytes against the configured `RAZORPAY_WEBHOOK_SECRET`.

## 4. PRE_EVENT vs POST_EVENT Semantics
- A webhook such as `payment.captured` received *after* authorization is considered **POST_EVENT risk intelligence**.
- Currently, assessments triggered by webhooks are not presented as pre-authorization blocks, since the authorization has already completed on Razorpay's end by the time the webhook is received. It is used for post-event review and auditing.

## 5. Model C Feature Incompatibility (CRITICAL)
A severe architectural mismatch exists between the validated **IEEE-CIS Model C** and the **Razorpay Webhook Payload**:

- **Model C Contract**: 147 IEEE-CIS raw features (yielding 438 transformed dimensions via an SKLearn pipeline). Over 54% of predictive weight relies on `V-series` (Vesta internal fields) and `id-series` (Identity telemetry).
- **Razorpay Payload**: Contains basic transactional metadata (`amount`, `currency`, `contact`, `email`).
- **Missing Features**: The Razorpay payload completely lacks all 86 `V-series` features, 21 `id-series` features, and proprietary `D-series` timedelta fields.
- **System Behavior**: The API detects this structural incompatibility automatically. Rather than faking unavailable features (which would silently corrupt the ML logic), `api/service.py` safely bypasses ML scoring. It returns an explicit `FEATURE_CONTRACT_UNAVAILABLE` evidence flag and gracefully falls back to deterministic decision logic (`REVIEW`), preserving system stability and scientific integrity without modifying the frozen Model C.

## 6. Scientific Conclusion
To score live Razorpay transactions with an ML model, one of two paths must be taken in the future:
1. **New Serving Adapter Model**: Train a new lightweight model strictly on the limited feature subset available from Razorpay webhooks.
2. **Device Intelligence Integration**: Inject comprehensive client-side fingerprinting (equivalent to `V-series` and `id-series`) into the Razorpay payload notes during client checkout, fulfilling the current Model C contract.

