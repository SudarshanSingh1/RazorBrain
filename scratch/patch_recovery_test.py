import re

with open("tests/test_event_recovery.py", "r") as f:
    text = f.read()

text = text.replace("@pytest.mark.asyncio\nasync def test_publication_failure_leaves_persisted():",
"""def test_publication_failure_leaves_persisted():
    asyncio.run(_test_publication_failure_leaves_persisted())

async def _test_publication_failure_leaves_persisted():""")

with open("tests/test_event_recovery.py", "w") as f:
    f.write(text)
