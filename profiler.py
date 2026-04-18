"""Statistical profiler: benchmarks a CSV dataset for quantum suitability."""

import json
import logging

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import LinearSVC

logger = logging.getLogger(__name__)

ABORT_LINEAR_THRESHOLD = 0.90
ABORT_PCA_THRESHOLD = 16
ABORT_ROWS_THRESHOLD = 50_000


def profile(csv_path: str, target_column: str) -> dict:
    """Load CSV, compute statistical benchmarks, return metadata dict.

    Raises ValueError if the target column is not found.
    Flags 'abort' key with reason if any hard limit is breached.
    """
    logger.info("Loading dataset from %s", csv_path)
    df = pd.read_csv(csv_path)

    if target_column not in df.columns:
        raise ValueError(f"Target column '{target_column}' not found in dataset.")

    df = df.dropna()
    row_count = len(df)
    col_count = len(df.columns) - 1
    logger.debug("Dataset shape after dropna: %d rows × %d features", row_count, col_count)

    X = df.drop(columns=[target_column])
    y = df[target_column]

    # Encode categorical features
    for col in X.select_dtypes(include=["object", "category"]).columns:
        X[col] = LabelEncoder().fit_transform(X[col].astype(str))

    le = LabelEncoder()
    y_enc = le.fit_transform(y.astype(str))
    n_classes = len(le.classes_)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Linear separability via LinearSVC
    logger.info("Computing linear separability score...")
    lsvc = LinearSVC(C=1000, max_iter=5000)
    lsvc.fit(X_scaled, y_enc)
    linear_svc_acc = float(np.mean(lsvc.predict(X_scaled) == y_enc))
    logger.debug("LinearSVC accuracy: %.4f", linear_svc_acc)

    # Classical complexity via RandomForest
    logger.info("Computing RandomForest score...")
    rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    rf.fit(X_scaled, y_enc)
    rf_acc = float(np.mean(rf.predict(X_scaled) == y_enc))
    complexity_gap = round(rf_acc - linear_svc_acc, 4)
    logger.debug("RandomForest accuracy: %.4f  |  Complexity gap: %.4f", rf_acc, complexity_gap)

    # PCA 95% variance component count
    logger.info("Computing PCA variance...")
    max_components = min(X_scaled.shape[0], X_scaled.shape[1])
    pca = PCA(n_components=max_components)
    pca.fit(X_scaled)
    cumulative_variance = np.cumsum(pca.explained_variance_ratio_)
    pca_95_count = int(np.searchsorted(cumulative_variance, 0.95) + 1)
    logger.debug("PCA components for 95%% variance: %d", pca_95_count)

    metadata = {
        "rows": row_count,
        "features": col_count,
        "n_classes": n_classes,
        "linear_svc_acc": round(linear_svc_acc, 4),
        "rf_acc": round(rf_acc, 4),
        "complexity_gap": complexity_gap,
        "pca_95_count": pca_95_count,
    }

    # Evaluate hard abort conditions
    abort_reason = None
    if linear_svc_acc > ABORT_LINEAR_THRESHOLD:
        abort_reason = (
            f"LinearSVC accuracy {linear_svc_acc:.4f} > {ABORT_LINEAR_THRESHOLD}: "
            "dataset is classically trivial."
        )
    elif pca_95_count > ABORT_PCA_THRESHOLD:
        abort_reason = (
            f"PCA 95%% variance requires {pca_95_count} components > {ABORT_PCA_THRESHOLD}: "
            "exceeds QPU qubit limit."
        )
    elif row_count > ABORT_ROWS_THRESHOLD:
        abort_reason = (
            f"Dataset has {row_count} rows > {ABORT_ROWS_THRESHOLD}: "
            "classical methods are more efficient."
        )

    if abort_reason:
        metadata["abort"] = abort_reason
        logger.warning("ABORT condition detected: %s", abort_reason)

    logger.debug("Profile metadata:\n%s", json.dumps(metadata, indent=2))
    return metadata
