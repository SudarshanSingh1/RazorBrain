import os
import json
import logging
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

RAW_DATA_PATH = "data/RAW/train_transaction.csv"
OUTPUT_DIR = "data/razorpay_serving_dataset"
CONTRACT_PATH = "data/razorpay_serving_feature_contract.json"
DOCS_PATH = "docs/razorpay_serving_dataset.md"

def build_features():
    logger.info("Loading raw IEEE-CIS transaction data...")
    if not os.path.exists(RAW_DATA_PATH):
        raise FileNotFoundError(f"Missing {RAW_DATA_PATH}")

    cols = ['TransactionID', 'isFraud', 'TransactionDT', 'TransactionAmt', 'P_emaildomain', 'card1', 'card4', 'card6']
    df = pd.read_csv(RAW_DATA_PATH, usecols=cols)
    
    logger.info("Sorting chronologically by TransactionDT...")
    df = df.sort_values('TransactionDT').reset_index(drop=True)

    logger.info("Building static features...")
    df['amount'] = df['TransactionAmt']
    df['log_amount'] = np.log1p(df['amount'])
    
    df['hour_of_day'] = (df['TransactionDT'] % 86400) // 3600
    df['day_of_week'] = (df['TransactionDT'] // 86400) % 7
    
    df['email_domain'] = df['P_emaildomain'].fillna('MISSING')
    df['email_domain_missing'] = df['P_emaildomain'].isna().astype(int)
    df['card_network'] = df['card4'].fillna('MISSING')
    df['card_type'] = df['card6'].fillna('MISSING')

    logger.info("Building historical behavior features (entity=card1)...")
    df['previous_transaction_count'] = df.groupby('card1').cumcount()
    df['is_new_customer'] = (df['previous_transaction_count'] == 0).astype(int)
    
    shifted_amount = df.groupby('card1')['amount'].shift(1)
    df['avg_customer_amount'] = shifted_amount.groupby(df['card1']).expanding().mean().reset_index(level=0, drop=True)
    df['avg_customer_amount'] = df['avg_customer_amount'].fillna(0)
    
    df['amount_deviation'] = (df['amount'] - df['avg_customer_amount']).where(df['previous_transaction_count'] > 0, 0)
    df['amount_ratio'] = (df['amount'] / df['avg_customer_amount'].replace(0, np.nan)).fillna(1.0).where(df['previous_transaction_count'] > 0, 1.0)
    
    logger.info("Computing rolling time windows...")
    df['dt'] = pd.to_datetime(df['TransactionDT'], unit='s')
    df = df.set_index('dt')
    
    # We must sort by card1 and dt for grouped rolling
    df = df.sort_values(['card1', 'TransactionDT'])
    
    # Rolling 1h
    df['txns_last_1h'] = df.groupby('card1')['TransactionID'].rolling('1h').count().reset_index(level=0, drop=True) - 1
    # Rolling 24h
    df['txns_last_24h'] = df.groupby('card1')['TransactionID'].rolling('24h').count().reset_index(level=0, drop=True) - 1
    
    df = df.sort_values('TransactionDT').reset_index(drop=True)

    features = [
        'amount', 'log_amount', 'hour_of_day', 'day_of_week',
        'email_domain', 'email_domain_missing', 'card_network', 'card_type',
        'previous_transaction_count', 'is_new_customer', 'avg_customer_amount',
        'amount_deviation', 'amount_ratio', 'txns_last_1h', 'txns_last_24h'
    ]
    
    logger.info(f"Generated {len(features)} serving features.")
    
    n_rows = len(df)
    train_end = int(n_rows * 0.70)
    val_end = int(n_rows * 0.85)
    
    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    cols_to_save = ['TransactionID', 'TransactionDT', 'isFraud'] + features
    
    logger.info("Saving split datasets to csv...")
    train_df[cols_to_save].to_csv(os.path.join(OUTPUT_DIR, 'train.csv'), index=False)
    val_df[cols_to_save].to_csv(os.path.join(OUTPUT_DIR, 'validation.csv'), index=False)
    test_df[cols_to_save].to_csv(os.path.join(OUTPUT_DIR, 'test.csv'), index=False)
    
    def get_stats(d, name):
        f = d['isFraud'].sum()
        r = f / len(d) * 100
        return f"{name}: {len(d)} rows, {f} fraud ({r:.2f}%) | Time: {d['TransactionDT'].min()} - {d['TransactionDT'].max()}"
        
    logger.info(get_stats(train_df, "TRAIN"))
    logger.info(get_stats(val_df, "VALIDATION"))
    logger.info(get_stats(test_df, "TEST (RAZORPAY_SERVING_TEST)"))

    contract = {
        "metadata": {
            "version": "1.0",
            "model_track": "RAZORPAY_SERVING_MODEL",
            "description": "Feature-restricted contract mapping IEEE-CIS concepts to Razorpay webhook availability."
        },
        "features": [
            {
                "name": "amount",
                "type": "numeric",
                "training_source": "TransactionAmt",
                "serving_source": "payment.amount / 100",
                "semantic_status": "DIRECTLY_ALIGNED",
                "required": True,
                "description": "Transaction amount in primary currency units (Rupees)"
            },
            {
                "name": "log_amount",
                "type": "numeric",
                "training_source": "log1p(TransactionAmt)",
                "serving_source": "log1p(payment.amount / 100)",
                "semantic_status": "DIRECTLY_ALIGNED",
                "required": True,
                "description": "Log-scaled transaction amount"
            },
            {
                "name": "hour_of_day",
                "type": "numeric",
                "training_source": "(TransactionDT % 86400) // 3600",
                "serving_source": "payment.created_at hour",
                "semantic_status": "DIRECTLY_ALIGNED",
                "required": True,
                "description": "Hour of the day in local timezone (0-23)"
            },
            {
                "name": "day_of_week",
                "type": "numeric",
                "training_source": "(TransactionDT // 86400) % 7",
                "serving_source": "payment.created_at weekday",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": True,
                "description": "Pseudo day of week preserving 7-day cyclicality"
            },
            {
                "name": "email_domain",
                "type": "categorical",
                "training_source": "P_emaildomain",
                "serving_source": "payment.email domain",
                "semantic_status": "DIRECTLY_ALIGNED",
                "required": False,
                "missing_representation": "MISSING",
                "description": "Email provider domain"
            },
            {
                "name": "email_domain_missing",
                "type": "numeric",
                "training_source": "P_emaildomain isna",
                "serving_source": "payment.email is None",
                "semantic_status": "DIRECTLY_ALIGNED",
                "required": True,
                "description": "Binary indicator for missing email"
            },
            {
                "name": "card_network",
                "type": "categorical",
                "training_source": "card4",
                "serving_source": "payment.card.network",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": False,
                "missing_representation": "MISSING",
                "description": "Card network (Visa, Mastercard, etc). MISSING for non-card payments."
            },
            {
                "name": "card_type",
                "type": "categorical",
                "training_source": "card6",
                "serving_source": "payment.card.type",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": False,
                "missing_representation": "MISSING",
                "description": "Card type (credit, debit). MISSING for non-card payments."
            },
            {
                "name": "previous_transaction_count",
                "type": "numeric",
                "training_source": "groupby(card1) cumcount",
                "serving_source": "Database: COUNT(transactions) for customer_id before current timestamp",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": True,
                "description": "Number of previous transactions by this entity"
            },
            {
                "name": "is_new_customer",
                "type": "numeric",
                "training_source": "previous_transaction_count == 0",
                "serving_source": "Database: previous_transaction_count == 0",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": True,
                "description": "Binary indicator for first-time entity"
            },
            {
                "name": "avg_customer_amount",
                "type": "numeric",
                "training_source": "groupby(card1) expanding mean (shifted)",
                "serving_source": "Database: AVG(amount) for customer_id before current timestamp",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": True,
                "description": "Historical average transaction amount for entity"
            },
            {
                "name": "amount_deviation",
                "type": "numeric",
                "training_source": "amount - avg_customer_amount",
                "serving_source": "amount - Database AVG(amount)",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": True,
                "description": "Deviation from historical average amount"
            },
            {
                "name": "amount_ratio",
                "type": "numeric",
                "training_source": "amount / avg_customer_amount",
                "serving_source": "amount / Database AVG(amount)",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": True,
                "description": "Ratio of current amount to historical average amount"
            },
            {
                "name": "txns_last_1h",
                "type": "numeric",
                "training_source": "Count prior rows where dt >= dt - 3600s",
                "serving_source": "Database: COUNT(transactions) in last hour for customer_id",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": True,
                "description": "Entity transaction velocity over 1 hour window"
            },
            {
                "name": "txns_last_24h",
                "type": "numeric",
                "training_source": "Count prior rows where dt >= dt - 86400s",
                "serving_source": "Database: COUNT(transactions) in last 24 hours for customer_id",
                "semantic_status": "CONCEPTUALLY_ALIGNED",
                "required": True,
                "description": "Entity transaction velocity over 24 hour window"
            }
        ]
    }
    
    with open(CONTRACT_PATH, "w") as f:
        json.dump(contract, f, indent=4)
        
    logger.info(f"Feature contract written to {CONTRACT_PATH}")

if __name__ == "__main__":
    build_features()
