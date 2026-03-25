"""
preprocess.py — Clean and split feature matrix into train/test sets.

Inputs:
    data.parquet — raw feature matrix from data.py

Outputs:
    train.parquet — training set (observation window users)
    test.parquet  — test set (temporally later users)

Uses temporal splitting: users who were last active earlier go into training,
more recently active users go into test. This prevents data leakage from
future behavior informing past predictions.
"""

import os

import pandas as pd

# ── Config ──────────────────────────────────────────────────────────────────

INPUT_PATH = os.environ.get("DATA_OUTPUT_PATH", "/tmp/data.parquet")
TRAIN_PATH = os.environ.get("TRAIN_OUTPUT_PATH", "/tmp/train.parquet")
TEST_PATH = os.environ.get("TEST_OUTPUT_PATH", "/tmp/test.parquet")

TEST_FRACTION = 0.25
TEMPORAL_GAP_ROWS = 50  # rows to skip between train and test as a buffer


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    df = pd.read_parquet(INPUT_PATH)
    print(f"Loaded {len(df)} rows from {INPUT_PATH}")

    # Sort by recency: users with larger days_since_last_event were active earlier
    # They go into training; more recent users go into test
    df = df.sort_values("days_since_last_event", ascending=False).reset_index(drop=True)

    # Fill NaN values
    label_col = "label"
    feature_cols = [c for c in df.columns if c not in {"person_id", label_col}]
    df[feature_cols] = df[feature_cols].fillna(0)

    # Temporal split with gap
    n_test = int(len(df) * TEST_FRACTION)
    split_point = len(df) - n_test - TEMPORAL_GAP_ROWS

    if split_point < 100:
        print(f"WARNING: Only {split_point} training rows. Results may be unreliable.")

    train_df = df.iloc[:split_point].copy()
    test_df = df.iloc[split_point + TEMPORAL_GAP_ROWS :].copy()

    train_pos = int(train_df[label_col].sum())
    test_pos = int(test_df[label_col].sum())

    print(f"Train: {len(train_df)} rows ({train_pos} positive, {len(train_df) - train_pos} negative)")
    print(f"Test:  {len(test_df)} rows ({test_pos} positive, {len(test_df) - test_pos} negative)")
    print(f"Gap:   {TEMPORAL_GAP_ROWS} rows skipped")

    if train_pos < 30:
        print(f"WARNING: Only {train_pos} positive examples in training set.")
    if test_pos < 10:
        print(f"WARNING: Only {test_pos} positive examples in test set.")

    train_df.to_parquet(TRAIN_PATH, index=False)
    test_df.to_parquet(TEST_PATH, index=False)
    print(f"Saved train to {TRAIN_PATH}")
    print(f"Saved test to {TEST_PATH}")


if __name__ == "__main__":
    main()
