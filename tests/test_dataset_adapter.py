import pytest
import pandas as pd
from data.dataset_adapter import IEEEDataAdapter

def test_missing_files_behavior(tmp_path):
    adapter = IEEEDataAdapter(data_dir=str(tmp_path))
    with pytest.raises(FileNotFoundError):
        adapter.load_and_join()

def test_fixture_loading_and_join(tmp_path):
    # Create small valid fixtures
    tx_df = pd.DataFrame({
        "TransactionID": [1, 2],
        "isFraud": [0, 1],
        "TransactionDT": [86400, 86401],
        "TransactionAmt": [10.5, 20.0],
        "card1": [1234, 5678]
    })
    
    id_df = pd.DataFrame({
        "TransactionID": [2],
        "DeviceType": ["mobile"]
    })
    
    tx_df.to_csv(tmp_path / "train_transaction.csv", index=False)
    id_df.to_csv(tmp_path / "train_identity.csv", index=False)
    
    adapter = IEEEDataAdapter(data_dir=str(tmp_path))
    result = adapter.load_and_join()
    
    assert len(result) == 2
    assert "DeviceType" in result.columns
    # Check left join is correct
    assert pd.isna(result.loc[result["TransactionID"] == 1, "DeviceType"].iloc[0])
    assert result.loc[result["TransactionID"] == 2, "DeviceType"].iloc[0] == "mobile"

def test_malformed_schema_behavior(tmp_path):
    # Create fixture missing required 'isFraud'
    tx_df = pd.DataFrame({
        "TransactionID": [1],
        "TransactionDT": [86400],
        "TransactionAmt": [10.5]
    })
    
    id_df = pd.DataFrame({
        "TransactionID": [1],
        "DeviceType": ["mobile"]
    })
    
    tx_df.to_csv(tmp_path / "train_transaction.csv", index=False)
    id_df.to_csv(tmp_path / "train_identity.csv", index=False)
    
    adapter = IEEEDataAdapter(data_dir=str(tmp_path))
    with pytest.raises(ValueError, match="Missing required column"):
        adapter.load_and_join()
