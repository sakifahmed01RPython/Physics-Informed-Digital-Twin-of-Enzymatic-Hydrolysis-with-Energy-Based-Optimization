import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import LeaveOneOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer

DATA_DIR = "data/processed"

PROCESS_COLS = ["Temp_C", "pH", "Duration_min", "SubstrateConc_gL"]
COMPOSITION_COLS = ["Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
                    "Hydroxyproline_pct", "Collagen_pct"]
OUTCOME_COLS = ["FinalDH_pct", "ProteinRecovery_pct"]
ENZYME_COL = "Enzyme"
TARGET = "ORAC"


def load_data():
    main = pd.read_csv(f"{DATA_DIR}/main_batch_clean.csv")
    ba = pd.read_csv(f"{DATA_DIR}/bioactivity_clean.csv")
    df = main.merge(ba, on="BatchID", how="inner")
    return df


def build_features(df):
    numeric = PROCESS_COLS + COMPOSITION_COLS + OUTCOME_COLS
    X = df[numeric].astype(float)
    enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    e = enc.fit_transform(df[[ENZYME_COL]])
    e_df = pd.DataFrame(e, columns=enc.get_feature_names_out([ENZYME_COL]), index=df.index)
    X = pd.concat([X, e_df], axis=1)
    return X, enc


def run_loo(df, alpha):
    X, enc = build_features(df)
    y = df[TARGET].to_numpy()
    loo = LeaveOneOut()
    preds = np.zeros(len(df))
    for train_idx, test_idx in loo.split(X):
        model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
        model.fit(X.iloc[train_idx], y[train_idx])
        preds[test_idx] = model.predict(X.iloc[test_idx])
    r2 = r2_score(y, preds)
    mae = mean_absolute_error(y, preds)
    return r2, mae, X, y


def main():
    df = load_data()
    print(f"Rows: {len(df)}, enzymes: {sorted(df[ENZYME_COL].unique())}, ORAC range {df[TARGET].min():.0f}-{df[TARGET].max():.0f}")
    best = None
    for alpha in [0.1, 1.0, 10.0, 100.0, 1000.0]:
        r2, mae, _, _ = run_loo(df, alpha)
        print(f"alpha={alpha:>6.1f}  LOO R2={r2:>6.3f}  MAE={mae:>6.2f}")
        if best is None or r2 > best[0]:
            best = (r2, mae, alpha)
    r2, mae, alpha = best
    print(f"Best: alpha={alpha}, LOO R2={r2:.3f}, MAE={mae:.2f} umol TE/g")
    pipeline = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    X, enc = build_features(df)
    pipeline.fit(X, df[TARGET])
    import joblib
    from pathlib import Path
    Path("models").mkdir(exist_ok=True)
    joblib.dump({"pipeline": pipeline, "onehot": enc}, "models/orac_ridge.joblib")
    print("Saved: models/orac_ridge.joblib")


if __name__ == "__main__":
    main()