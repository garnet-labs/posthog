"""
preprocess.py — Clean and split feature matrix into train/test sets.

Inputs:
    data.parquet — raw feature matrix from data.py
        Required columns: person_id, label, plus feature columns

Outputs:
    train.parquet — training set (stratified random sample)
    test.parquet  — test set (stratified random sample)

Checks:
    - label column exists and is binary
    - no duplicate person_ids
    - minimum positive examples in both splits
    - feature columns have no all-null columns
"""

import os
import sys

import numpy as np
import pandas as pd

# ── Config ──────────────────────────────────────────────────────────────────

INPUT_PATH = os.environ.get("DATA_OUTPUT_PATH", "/tmp/data.parquet")
TRAIN_PATH = os.environ.get("TRAIN_OUTPUT_PATH", "/tmp/train.parquet")
TEST_PATH = os.environ.get("TEST_OUTPUT_PATH", "/tmp/test.parquet")

TEST_FRACTION = 0.25
MAX_USERS = int(os.environ.get("MAX_USERS", "10000"))
SEED = 42


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    df = pd.read_parquet(INPUT_PATH)
    print(f"Loaded {len(df)} rows from {INPUT_PATH}")

    # ── Checks ───────────────────────────────────────────────────────────
    label_col = "label"

    if label_col not in df.columns:
        print(f"ERROR: Missing '{label_col}' column.")
        sys.exit(1)

    if "person_id" not in df.columns:
        print("ERROR: Missing 'person_id' column.")
        sys.exit(1)

    dupes = df["person_id"].duplicated().sum()
    if dupes > 0:
        print(f"WARNING: {dupes} duplicate person_ids found. Dropping duplicates.")
        df = df.drop_duplicates(subset="person_id", keep="first")

    unique_labels = df[label_col].unique()
    if not set(unique_labels).issubset({0, 1}):
        print(f"ERROR: label column has unexpected values: {unique_labels}")
        sys.exit(1)

    # ── Clean ────────────────────────────────────────────────────────────
    feature_cols = [c for c in df.columns if c not in {"person_id", label_col}]
    df[feature_cols] = df[feature_cols].fillna(0)

    # Drop all-zero feature columns
    zero_cols = [c for c in feature_cols if (df[c] == 0).all()]
    if zero_cols:
        print(f"Dropping {len(zero_cols)} all-zero columns: {zero_cols}")
        df = df.drop(columns=zero_cols)

    # ── Sample ───────────────────────────────────────────────────────────
    if len(df) > MAX_USERS:
        print(f"Sampling {MAX_USERS} users from {len(df)} (preserving positive ratio)")
        pos = df[df[label_col] == 1]
        neg = df[df[label_col] == 0]
        pos_ratio = len(pos) / len(df)
        n_pos = max(int(MAX_USERS * pos_ratio), len(pos))  # keep all positives if possible
        n_neg = MAX_USERS - min(n_pos, len(pos))
        sampled_pos = pos.sample(n=min(n_pos, len(pos)), random_state=SEED)
        sampled_neg = neg.sample(n=min(n_neg, len(neg)), random_state=SEED)
        df = pd.concat([sampled_pos, sampled_neg]).reset_index(drop=True)
        print(f"Sampled: {len(df)} rows ({int(df[label_col].sum())} positive)")

    # ── Stratified split ─────────────────────────────────────────────────
    np.random.seed(SEED)

    pos_df = df[df[label_col] == 1].copy()
    neg_df = df[df[label_col] == 0].copy()

    pos_test_n = max(int(len(pos_df) * TEST_FRACTION), 1)
    neg_test_n = int(len(neg_df) * TEST_FRACTION)

    pos_shuffled = pos_df.sample(frac=1, random_state=SEED)
    neg_shuffled = neg_df.sample(frac=1, random_state=SEED)

    test_df = pd.concat([pos_shuffled.iloc[:pos_test_n], neg_shuffled.iloc[:neg_test_n]])
    train_df = pd.concat([pos_shuffled.iloc[pos_test_n:], neg_shuffled.iloc[neg_test_n:]])

    train_df = train_df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    test_df = test_df.sample(frac=1, random_state=SEED).reset_index(drop=True)

    train_pos = int(train_df[label_col].sum())
    test_pos = int(test_df[label_col].sum())

    print(f"Train: {len(train_df)} rows ({train_pos} positive, {len(train_df) - train_pos} negative)")
    print(f"Test:  {len(test_df)} rows ({test_pos} positive, {len(test_df) - test_pos} negative)")

    # ── Final checks ─────────────────────────────────────────────────────
    if train_pos < 20:
        print(f"WARNING: Only {train_pos} positive examples in training set.")
    if test_pos < 5:
        print(f"WARNING: Only {test_pos} positive examples in test set.")

    # ── Save ─────────────────────────────────────────────────────────────
    train_df.to_parquet(TRAIN_PATH, index=False)
    test_df.to_parquet(TEST_PATH, index=False)
    print(f"Saved train to {TRAIN_PATH}")
    print(f"Saved test to {TEST_PATH}")


if __name__ == "__main__":
    main()
