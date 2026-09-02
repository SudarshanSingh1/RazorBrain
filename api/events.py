import asyncio
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from api.schemas import TransactionRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. Event Contracts
# ---------------------------------------------------------

class EventMetadata(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str
    
class TransactionEvent(BaseModel):
    metadata: EventMetadata
    payload: TransactionRequest
    
class AssessmentResultEvent(BaseModel):
    metadata: EventMetadata
    original_event_id: str
    status: str  # e.g., "SUCCESS", "FAILED"
    assessment_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------
# 2. Publisher / Consumer Interfaces
# ---------------------------------------------------------

class EventPublisher:
    async def publish(self, topic: str, event_data: dict) -> bool:
        raise NotImplementedError

class EventConsumer:
    async def consume(self) -> dict:
        raise NotImplementedError

# ---------------------------------------------------------
# 3. In-Memory Implementations
# ---------------------------------------------------------

class InMemoryEventBroker(EventPublisher, EventConsumer):
    """
    In-memory bounded broker for local processing.
    Provides backpressure by strictly limiting the queue size.
    """
    def __init__(self, max_size: int = 1000):
        self.queue = asyncio.Queue(maxsize=max_size)
        self.metrics = {
            "events_received": 0,
            "events_dropped": 0,
            "events_processed": 0
        }
        
    async def publish(self, topic: str, event_data: dict) -> bool:
        """Publishes an event. Fails immediately if queue is full (backpressure)."""
        try:
            self.queue.put_nowait({"topic": topic, "data": event_data})
            self.metrics["events_received"] += 1
            return True
        except asyncio.QueueFull:
            self.metrics["events_dropped"] += 1
            logger.warning(f"Broker queue is full (max {self.queue.maxsize}). Event dropped.")
            return False

    async def consume(self) -> dict:
        """Blocks until an event is available."""
        event = await self.queue.get()
        return event
        
    def ack(self):
        """Acknowledges successful processing of the current event."""
        self.queue.task_done()
        self.metrics["events_processed"] += 1

# ---------------------------------------------------------
# 4. Processing Lifecycle
# ---------------------------------------------------------

class EventProcessor:
    def __init__(
        self, 
        consumer: EventConsumer, 
        publisher: EventPublisher, 
        app_state
    ):
        self.consumer = consumer
        self.publisher = publisher
        self.state = app_state
        self._running = False
        
    async def start(self):
        self._running = True
        logger.info("EventProcessor started.")
        while self._running:
            try:
                # Wait for next event
                msg = await self.consumer.consume()
                if not msg:
                    continue
                    
                topic = msg.get("topic")
                data = msg.get("data")
                
                # Only process ingestion events
                if topic == "transaction.received":
                    await self._handle_transaction_received(data)
                    
                if hasattr(self.consumer, "ack"):
                    self.consumer.ack()
                    
            except asyncio.CancelledError:
                self._running = False
                logger.info("EventProcessor shut down cleanly.")
                break
            except Exception as e:
                logger.error(f"EventProcessor unhandled error: {e}")
                if hasattr(self.consumer, "ack"):
                    self.consumer.ack() # Do not block queue forever on poison pill

    async def _handle_transaction_received(self, event_dict: dict):
        """
        Executes the internal processing lifecycle.
        RECEIVED -> VALIDATED -> PROCESSING -> ASSESSED -> PERSISTED -> PUBLISHED
        """
        from fastapi.concurrency import run_in_threadpool
        from api.service import assess_transaction, DatabasePersistenceError
        from database.repository import DuplicateAssessmentError, DuplicateEventError, reserve_event, update_event_status
        from database.connection import get_session
        import time
        
        start_time = time.monotonic()
        
        try:
            # 1. Validation (Schema)
            event = TransactionEvent(**event_dict)
        except Exception as e:
            logger.error(f"Event validation failed: {e}")
            await self._publish_failure(event_dict, "VALIDATION_FAILED", str(e))
            return
            
        corr_id = event.metadata.correlation_id
        event_id = event.metadata.event_id
        txn_dict = event.payload.model_dump()
        
        logger.info(f"[{corr_id}] PROCESSING started for event {event_id}")
        
        # 2. Event Idempotency Check (Persistent)
        try:
            with get_session(self.state.db_path) as conn:
                reserve_event(conn, event_id, corr_id)
        except DuplicateEventError as e:
            logger.warning(f"[{corr_id}] Duplicate event {event_id} delivered. Dropping.")
            await self._publish_failure(event_dict, "DUPLICATE_EVENT", str(e), corr_id=corr_id)
            return
        except Exception as e:
            logger.error(f"[{corr_id}] Event ledger error: {e}")
            await self._publish_failure(event_dict, "PROCESSING_FAILED", str(e), corr_id=corr_id)
            return
            
        try:
            # 3. Risk Assessment (CPU bound, run in threadpool)
            assessment_record = await run_in_threadpool(assess_transaction, txn_dict, self.state)
            
            # 4. Persistence Success
            duration = time.monotonic() - start_time
            logger.info(f"[{corr_id}] ASSESSED and PERSISTED in {duration:.4f}s")
            
            with get_session(self.state.db_path) as conn:
                update_event_status(conn, event_id, "PERSISTED", assessment_record.get("assessment_id"))
            
            result_event = AssessmentResultEvent(
                metadata=EventMetadata(
                    event_type="transaction.assessed",
                    correlation_id=corr_id
                ),
                original_event_id=event_id,
                status="PERSISTED", # explicitly denoting what succeeded
                assessment_payload=assessment_record
            )
            
            # 5. Publish Result
            try:
                success = await self.publisher.publish("transaction.assessed", result_event.model_dump())
                with get_session(self.state.db_path) as conn:
                    if success:
                        update_event_status(conn, event_id, "PUBLISHED")
                    else:
                        update_event_status(conn, event_id, "PUBLICATION_FAILED")
            except Exception as e:
                logger.error(f"[{corr_id}] PUBLICATION_FAILED: {e}")
                with get_session(self.state.db_path) as conn:
                    update_event_status(conn, event_id, "PUBLICATION_FAILED")
                # Do not re-raise, the event processing is COMPLETE and PERSISTED.

                    
        except DuplicateAssessmentError as e:
            logger.warning(f"[{corr_id}] Duplicate assessment handled via idempotency.")
            with get_session(self.state.db_path) as conn:
                update_event_status(conn, event_id, "DUPLICATE_ASSESSMENT")
            await self._publish_failure(event_dict, "DUPLICATE_ASSESSMENT", str(e), corr_id=corr_id)
            
        except DatabasePersistenceError as e:
            logger.error(f"[{corr_id}] Persistence failed: {e}")
            with get_session(self.state.db_path) as conn:
                update_event_status(conn, event_id, "PERSISTENCE_FAILED")
                
            result_event = AssessmentResultEvent(
                metadata=EventMetadata(
                    event_type="transaction.failed",
                    correlation_id=corr_id
                ),
                original_event_id=event_id,
                status="PERSISTENCE_FAILED",
                assessment_payload=e.decision_result,
                error_message=str(e)
            )
            await self.publisher.publish("transaction.failed", result_event.model_dump())
            
        except Exception as e:
            logger.error(f"[{corr_id}] PROCESSING_FAILED: {e}")
            with get_session(self.state.db_path) as conn:
                update_event_status(conn, event_id, "PROCESSING_FAILED")
            await self._publish_failure(event_dict, "PROCESSING_FAILED", str(e), corr_id=corr_id)
    async def _publish_failure(self, event_dict: dict, status: str, message: str, corr_id: str = "unknown"):
        meta = event_dict.get("metadata", {})
        orig_event_id = meta.get("event_id", "unknown")
        cid = meta.get("correlation_id", corr_id)
        
        result_event = AssessmentResultEvent(
            metadata=EventMetadata(
                event_type="transaction.failed",
                correlation_id=cid
            ),
            original_event_id=orig_event_id,
            status=status,
            error_message=message
        )
        await self.publisher.publish("transaction.failed", result_event.model_dump())

    def stop(self):
        self._running = False
