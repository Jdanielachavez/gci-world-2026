"""v3 — adds position-relative percentile features + CatBoost native categoricals."""
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import lightgbm as lgb
import xgboost as xgb
from catboost import CatBoostClassifier, Pool
from scipy.stats import rankdata
import warnings
warnings.filterwarnings('ignore')

SEED = 42
np.random.seed(SEED)

train = pd.read_csv('train.csv')
test = pd.read_csv('test.csv')
n_train = len(train)

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
    perf = ['Sprint_40yd', 'Vertical_Jump', 'Bench_Press_Reps', 'Broad_Jump', 'Agility_3cone', 'Shuttle', 'Age']
    df['Missing_Count'] = df[perf].isnull().sum(axis=1)
    # Momentum/speed-mass physics composites
    df['Speed_Score'] = (df['Weight'] * 200) / (df['Sprint_40yd'] ** 4)
    df['Momentum'] = df['Weight'] / df['Sprint_40yd']
    return df

train = create_features(train)
test = create_features(test)

# Position-relative percentiles computed on combined data (no target used)
combined = pd.concat([train, test], ignore_index=True)
metric_cols = ['Sprint_40yd', 'Vertical_Jump', 'Bench_Press_Reps', 'Broad_Jump',
               'Agility_3cone', 'Shuttle', 'Weight', 'Height', 'BMI', 'Speed_Score', 'Momentum']
for col in metric_cols:
    combined[f'{col}_pos_pct'] = combined.groupby('Position')[col].rank(pct=True)
    combined[f'{col}_year_pct'] = combined.groupby('Year')[col].rank(pct=True)

train = combined.iloc[:n_train].copy()
test = combined.iloc[n_train:].copy()

all_school = pd.concat([train['School'], test['School']])
school_freq = all_school.value_counts()
train['School_Freq'] = train['School'].map(school_freq)
test['School_Freq'] = test['School'].map(school_freq)

cat_cols = [c for c in ['School', 'Player_Type', 'Position_Type', 'Position'] if c in train.columns]
for c in cat_cols:
    le = LabelEncoder()
    le.fit(pd.concat([train[c], test[c]]).astype(str))
    train[c + '_LE'] = le.transform(train[c].astype(str))
    test[c + '_LE'] = le.transform(test[c].astype(str))

target = train['Drafted']
drop_cols = ['Id', 'Drafted'] + cat_cols
feat_cols = [c for c in train.columns if c not in drop_cols]
X = train[feat_cols].copy()
X_test = test[feat_cols].copy()
print(f"Features: {len(feat_cols)}")

def oof_target_encode(tr_series, te_series, y, n_splits=5, smooth=10):
    gm = y.mean()
    oof = pd.Series(np.nan, index=tr_series.index)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=SEED)
    for tr_idx, val_idx in skf.split(tr_series, y):
        ft, fy = tr_series.iloc[tr_idx], y.iloc[tr_idx]
        st = fy.groupby(ft).agg(['mean', 'count'])
        enc = (st['mean'] * st['count'] + gm * smooth) / (st['count'] + smooth)
        oof.iloc[val_idx] = tr_series.iloc[val_idx].map(enc)
    oof = oof.fillna(gm)
    st = y.groupby(tr_series).agg(['mean', 'count'])
    enc = (st['mean'] * st['count'] + gm * smooth) / (st['count'] + smooth)
    return oof, te_series.map(enc).fillna(gm)

tr_school = train['School'].astype(str).reset_index(drop=True)
te_school = test['School'].astype(str).reset_index(drop=True)
X = X.reset_index(drop=True); X_test = X_test.reset_index(drop=True); target = target.reset_index(drop=True)
X['School_TE'], X_test['School_TE'] = oof_target_encode(tr_school, te_school, target)

means = X.mean()
Xi = X.fillna(means)
Xi_test = X_test.fillna(means)

# CatBoost native categorical version (handles NaN natively)
cb_train = train[feat_cols + cat_cols].reset_index(drop=True)
cb_test = test[feat_cols + cat_cols].reset_index(drop=True)
for c in cat_cols:
    cb_train[c] = cb_train[c].astype(str)
    cb_test[c] = cb_test[c].astype(str)

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
results = {}

# Model A: CatBoost native cats
oof = np.zeros(n_train); tp = np.zeros(len(cb_test))
for tr_idx, val_idx in skf.split(cb_train, target):
    m = CatBoostClassifier(iterations=1200, learning_rate=0.025, depth=6, l2_leaf_reg=3,
                           random_seed=SEED, verbose=0, cat_features=cat_cols)
    m.fit(cb_train.iloc[tr_idx], target.iloc[tr_idx])
    oof[val_idx] = m.predict_proba(cb_train.iloc[val_idx])[:, 1]
    tp += m.predict_proba(cb_test)[:, 1] / 5
results['cat_native'] = (oof, tp, roc_auc_score(target, oof))
print(f"cat_native: {results['cat_native'][2]:.5f}")

# Model B: LightGBM
oof = np.zeros(n_train); tp = np.zeros(len(Xi_test))
for tr_idx, val_idx in skf.split(Xi, target):
    m = lgb.LGBMClassifier(n_estimators=800, learning_rate=0.02, num_leaves=31, subsample=0.8,
                           colsample_bytree=0.7, reg_alpha=0.1, reg_lambda=1.0, random_state=SEED, verbose=-1)
    m.fit(Xi.iloc[tr_idx], target.iloc[tr_idx])
    oof[val_idx] = m.predict_proba(Xi.iloc[val_idx])[:, 1]
    tp += m.predict_proba(Xi_test)[:, 1] / 5
results['lgb'] = (oof, tp, roc_auc_score(target, oof))
print(f"lgb: {results['lgb'][2]:.5f}")

# Model C: XGBoost
oof = np.zeros(n_train); tp = np.zeros(len(Xi_test))
for tr_idx, val_idx in skf.split(Xi, target):
    m = xgb.XGBClassifier(n_estimators=800, learning_rate=0.02, max_depth=5, subsample=0.8,
                          colsample_bytree=0.7, reg_alpha=0.1, reg_lambda=1.0, random_state=SEED,
                          eval_metric='auc', verbosity=0)
    m.fit(Xi.iloc[tr_idx], target.iloc[tr_idx])
    oof[val_idx] = m.predict_proba(Xi.iloc[val_idx])[:, 1]
    tp += m.predict_proba(Xi_test)[:, 1] / 5
results['xgb'] = (oof, tp, roc_auc_score(target, oof))
print(f"xgb: {results['xgb'][2]:.5f}")

# Model D: RandomForest
oof = np.zeros(n_train); tp = np.zeros(len(Xi_test))
for tr_idx, val_idx in skf.split(Xi, target):
    m = RandomForestClassifier(n_estimators=600, max_depth=12, min_samples_leaf=4, random_state=SEED, n_jobs=-1)
    m.fit(Xi.iloc[tr_idx], target.iloc[tr_idx])
    oof[val_idx] = m.predict_proba(Xi.iloc[val_idx])[:, 1]
    tp += m.predict_proba(Xi_test)[:, 1] / 5
results['rf'] = (oof, tp, roc_auc_score(target, oof))
print(f"rf: {results['rf'][2]:.5f}")

# Rank-average ensemble
w = {k: max(v[2] - 0.5, 0.001) for k, v in results.items()}
tot = sum(w.values())
ens_oof = sum(rankdata(results[k][0]) / n_train * w[k] / tot for k in results)
ens_test = sum(rankdata(results[k][1]) / len(Xi_test) * w[k] / tot for k in results)
print(f"ENSEMBLE OOF: {roc_auc_score(target, ens_oof):.5f}")

sub = pd.DataFrame({'Id': test['Id'].astype(int), 'Drafted': ens_test})
sub.to_csv('submission_v3.csv', index=False)
print("Saved submission_v3.csv")
