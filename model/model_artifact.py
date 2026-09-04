import os
import logging
import joblib
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ModelUnavailableError(Exception):
    pass

class InvalidModelArtifactError(Exception):
    pass

def load_model_artifact(model_path: str = "data/model_c_calibrated.joblib") -> Optional[Dict[str, Any]]:
    """
    Locates and loads the configured CALIBRATED model artifact bundle.
    Production scoring MUST use the calibrated artifact.
    """
    if not os.path.exists(model_path):
        logger.error(f"Model artifact not found at {model_path}. Cannot fallback to training or uncalibrated.")
        raise ModelUnavailableError(f"Calibrated artifact missing: {model_path}")
        
    try:
        artifact = joblib.load(model_path)
    except Exception as e:
        logger.error(f"Failed to deserialize model artifact at {model_path}: {e}")
        raise InvalidModelArtifactError(f"Deserialization failed: {e}")
        
    # Validate structure
    required_keys = [
        "base_model_artifact", 
        "calibrator", 
        "calibrator_method",
        "calibrated_at"
    ]
    
    for k in required_keys:
        if k not in artifact:
            logger.error(f"Invalid model artifact: missing key '{k}'.")
            raise InvalidModelArtifactError(f"Missing {k} in calibrated artifact.")
            
    logger.info(f"Successfully loaded and validated calibrated model artifact from {model_path}")
    return artifact
