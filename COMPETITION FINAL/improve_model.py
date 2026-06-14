"""Improved NFL Draft model — fixes target-encoding leakage with out-of-fold encoding,
uses robust CV ensemble. Goal: lift public score from 0.80 toward ~0.85."""
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
from sklearn.ensemble import RandomForestClassifier
import lightgbm as lgb
import xgboost as xgb
from catboost import CatBoostClassifier
import warnings
warnings.filterwarnings('ignore')

SEED = 42
np.random.seed(SEED)

train = pd.read_csv('train.csv')
test = pd.read_csv('test.csv')
print(f"Train: {train.shape}, Test: {test.shape}")

def create_features(df):
    df = df.copy()
    df['BMI'] = df['Weight'] / (df['Height'] ** 2)
    df['Weight_Height'] = df['Weight'] / df['Height']
    df['Power_Weight'] = df['Vertical_Jump'] / df['Weight']
    df['Broad_Weight'] = df['Broad_Jump'] / df['Weight']
    df['Strength_Weight'] = df['Bench_Press_Reps'] / df['Weight'] * 100
    df['Speed_Agility'] = df['Sprint_40yd'] + df['Agility_3cone']
    df['Speed_Shuttle'] = df['Sprint_40yd'] + df['Shuttle']
    df['Sprint_Height'] = df['Sprint_40yd'] / df['Height']
    df['Explosiveness'] = df['Vertical_Jump'] + df['Broad_Jump']
    perf_cols = ['Sprint_40yd', 'Vertical_Jump', 'Bench_Press_Reps',
                 'Broad_Jump', 'Agility_3cone', 'Shuttle', 'Age']
    df['Missing_Count'] = df[perf_cols].isnull().sum(axis=1)
    return df

train = create_features(train)
test = create_features(test)

# School frequency computed on combined data (no label leakage — uses no target)
all_school = pd.concat([train['School'], test['School']])
school_freq = all_school.value_counts()
train['School_Freq'] = train['School'].map(school_freq)
test['School_Freq'] = test['School'].map(school_freq)

# Label-encode categoricals consistently across train+test
from sklearn.preprocessing import LabelEncoder
cat_cols = [c for c in ['School', 'Player_Type', 'Position_Type', 'Position'] if c in train.columns]
for c in cat_cols:
    le = LabelEncoder()
    combined = pd.concat([train[c], test[c]]).astype(str)
    le.fit(combined)
    train[c + '_LE'] = le.transform(train[c].astype(str))
    test[c + '_LE'] = le.transform(test[c].astype(str))

target = train['Drafted']
drop_cols = ['Id', 'Drafted'] + cat_cols
feat_cols = [c for c in train.columns if c not in drop_cols]
X = train[feat_cols].copy()
X_test = test[feat_cols].copy()
print(f"Features ({len(feat_cols)}): {feat_cols}")

# Out-of-fold target encoding for School (leak-free, smoothed)
def oof_target_encode(tr_series, te_series, y, n_splits=5, smooth=10):
    global_mean = y.mean()
    oof = pd.Series(np.nan, index=tr_series.index)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=SEED)
    for tr_idx, val_idx in skf.split(tr_series, y):
        fold_tr = tr_series.iloc[tr_idx]
        fold_y = y.iloc[tr_idx]
        stats = fold_y.groupby(fold_tr).agg(['mean', 'count'])
        enc = (stats['mean'] * stats['count'] + global_mean * smooth) / (stats['count'] + smooth)
        oof.iloc[val_idx] = tr_series.iloc[val_idx].map(enc)
    oof = oof.fillna(global_mean)
    stats_full = y.groupby(tr_series).agg(['mean', 'count'])
    enc_full = (stats_full['mean'] * stats_full['count'] + global_mean * smooth) / (stats_full['count'] + smooth)
    te = te_series.map(enc_full).fillna(global_mean)
    return oof, te

X['School_TE'], X_test['School_TE'] = oof_target_encode(train['School'].astype(str), test['School'].astype(str), target)

# Mean imputation (fit on train only)
means = X.mean()
X = X.fillna(means)
X_test = X_test.fillna(means)

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
models = {
    'lgb': lambda: lgb.LGBMClassifier(n_estimators=600, learning_rate=0.03, num_leaves=31,
                                      subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
                                      random_state=SEED, verbose=-1),
    'xgb': lambda: xgb.XGBClassifier(n_estimators=600, learning_rate=0.03, max_depth=5,
                                     subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
                                     random_state=SEED, eval_metric='auc', verbosity=0),
    'cat': lambda: CatBoostClassifier(iterations=800, learning_rate=0.03, depth=6,
                                      l2_leaf_reg=3, random_seed=SEED, verbose=0),
    'rf':  lambda: RandomForestClassifier(n_estimators=500, max_depth=10, min_samples_leaf=5,
                                          random_state=SEED, n_jobs=-1),
}

oof_preds = {}
test_preds = {}
cv_scores = {}
for name, factory in models.items():
    oof = np.zeros(len(X))
    tp = np.zeros(len(X_test))
    for tr_idx, val_idx in skf.split(X, target):
        m = factory()
        m.fit(X.iloc[tr_idx], target.iloc[tr_idx])
        oof[val_idx] = m.predict_proba(X.iloc[val_idx])[:, 1]
        tp += m.predict_proba(X_test)[:, 1] / skf.n_splits
    auc = roc_auc_score(target, oof)
    oof_preds[name] = oof
    test_preds[name] = tp
    cv_scores[name] = auc
    print(f"{name}: OOF AUC = {auc:.5f}")

# Rank-average ensemble weighted by OOF AUC
from scipy.stats import rankdata
w = {k: max(v - 0.5, 0.001) for k, v in cv_scores.items()}
tot = sum(w.values())
ens_oof = sum(rankdata(oof_preds[k]) / len(X) * w[k] / tot for k in models)
ens_test = sum(rankdata(test_preds[k]) / len(X_test) * w[k] / tot for k in models)
ens_auc = roc_auc_score(target, ens_oof)
print(f"ENSEMBLE OOF AUC = {ens_auc:.5f}")

sub = pd.DataFrame({'Id': test['Id'], 'Drafted': ens_test})
sub.to_csv('submission_v2.csv', index=False)
print("Saved submission_v2.csv")
print(sub.head())
