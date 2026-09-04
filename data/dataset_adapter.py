import pandas as pd
from pathlib import Path
import logging
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)

class IEEEDataAdapter:
    """
    Adapter for loading and validating the IEEE-CIS Fraud Detection dataset.
    Responsible only for I/O, column validation, and providing a clean join.
    Does NOT perform final feature engineering or model training.
    """
    def __init__(self, data_dir: str = "data/RAW"):
        self.data_dir = Path(data_dir)
        self.transaction_path = self.data_dir / "train_transaction.csv"
        self.identity_path = self.data_dir / "train_identity.csv"

    def _validate_files_exist(self):
        if not self.transaction_path.exists():
            raise FileNotFoundError(f"IEEE-CIS transaction file not found: {self.transaction_path}")
        if not self.identity_path.exists():
            raise FileNotFoundError(f"IEEE-CIS identity file not found: {self.identity_path}")

    def load_and_join(self, nrows: Optional[int] = None) -> pd.DataFrame:
        """
        Loads the transaction and identity files and joins them on TransactionID.
        """
        self._validate_files_exist()
        
        logger.info(f"Loading {self.transaction_path}...")
        df_tx = pd.read_csv(self.transaction_path, nrows=nrows)
        
        logger.info(f"Loading {self.identity_path}...")
        df_id = pd.read_csv(self.identity_path, nrows=nrows)
        
        # Validate critical columns
        required_tx = ["TransactionID", "isFraud", "TransactionDT", "TransactionAmt"]
        for col in required_tx:
            if col not in df_tx.columns:
                raise ValueError(f"Missing required column in transaction dataset: {col}")
                
        required_id = ["TransactionID"]
        for col in required_id:
            if col not in df_id.columns:
                raise ValueError(f"Missing required column in identity dataset: {col}")

        logger.info("Joining datasets on TransactionID...")
        df_joined = df_tx.merge(df_id, on="TransactionID", how="left")
        
        logger.info(f"Join complete. Resulting shape: {df_joined.shape}")
        return df_joined
