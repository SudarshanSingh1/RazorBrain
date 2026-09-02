import re

with open("api/events.py", "r") as f:
    text = f.read()

# I will wrap the publisher call in its own try/except block to isolate it.

old_block = """            # 5. Publish Result
            success = await self.publisher.publish("transaction.assessed", result_event.model_dump())
            with get_session(self.state.db_path) as conn:
                if success:
                    update_event_status(conn, event_id, "PUBLISHED")
                else:
                    update_event_status(conn, event_id, "PUBLICATION_FAILED")"""

new_block = """            # 5. Publish Result
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
"""

text = text.replace(old_block, new_block)

with open("api/events.py", "w") as f:
    f.write(text)
