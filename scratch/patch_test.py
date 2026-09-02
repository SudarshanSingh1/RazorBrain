import re

with open("tests/test_ui_contract.py", "r") as f:
    text = f.read()

text = text.replace('print("model_evidence raw result:", result["model_evidence"])\n            assert len(dash_data["model_evidence"]) > 0',
                    'assert len(dash_data["model_evidence"]) > 0')

text = text.replace('assert len(dash_data["model_evidence"]) > 0',
                    'print("\\nRAW MODEL EVIDENCE:", result.get("model_evidence"))\n            assert len(dash_data["model_evidence"]) > 0')

with open("tests/test_ui_contract.py", "w") as f:
    f.write(text)
