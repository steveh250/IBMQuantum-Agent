"""Generate two test datasets for Q-Agent CLI demonstration."""

import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

rng = np.random.default_rng(42)


# ─────────────────────────────────────────────────────────────────────────────
# Dataset 1: Test-DataSet-Abort
# Theme: Particle beam classification — two beam types with well-separated
#         physical signatures. A classical linear model handles this trivially,
#         making it a waste of QPU resources.
#
# Target abort trigger: LinearSVC accuracy >> 0.90
# ─────────────────────────────────────────────────────────────────────────────

N = 1000
half = N // 2

# Beam type A — high-energy protons: all features cluster around positive values
energy_A        = rng.normal(4.2,  0.35, half)
momentum_A      = rng.normal(3.8,  0.30, half)
transverse_A    = rng.normal(4.5,  0.40, half)
ionisation_A    = rng.normal(3.5,  0.25, half)
beam_label_A    = ["proton"] * half

# Beam type B — low-energy pions: all features cluster around negative values
energy_B        = rng.normal(-4.2, 0.35, half)
momentum_B      = rng.normal(-3.8, 0.30, half)
transverse_B    = rng.normal(-4.5, 0.40, half)
ionisation_B    = rng.normal(-3.5, 0.25, half)
beam_label_B    = ["pion"] * half

df_abort = pd.DataFrame({
    "energy_gev":          np.concatenate([energy_A,     energy_B]),
    "momentum_gev_c":      np.concatenate([momentum_A,   momentum_B]),
    "transverse_mom":      np.concatenate([transverse_A, transverse_B]),
    "ionisation_rate":     np.concatenate([ionisation_A, ionisation_B]),
    "particle_type":       beam_label_A + beam_label_B,
})

df_abort = df_abort.sample(frac=1, random_state=42).reset_index(drop=True)
abort_path = DATA_DIR / "test_dataset_abort.csv"
df_abort.to_csv(abort_path, index=False)
print(f"Saved ABORT dataset → {abort_path}  ({len(df_abort)} rows, {len(df_abort.columns)-1} features)")


# ─────────────────────────────────────────────────────────────────────────────
# Dataset 2: Test-DataSet-Run  (PoC-optimised for fast QPU execution)
# Theme: Quantum material phase classification (topological vs trivial insulator)
#
# Deliberately simplified for fast QPU execution:
#   • 4 features  → 4-qubit circuit (was 8). ZZ feature map with 4 qubits
#                   produces ~12 gates vs ~56 for 8 qubits.
#   • 200 samples → fewer COBYLA evaluations (was 900).
#   • reps=1      → shallower circuit depth (set in generator prompt).
#
# The non-linear phase boundary is driven by an XOR-like relationship between
# spin_orbit_coupling and crystal_field_eV — the two primary topological
# order parameters. LinearSVC cannot represent a 4-quadrant boundary, so the
# complexity gap remains high enough to justify a quantum kernel.
#
# Statistical targets:
#   linear_svc_acc  ≈ 0.55–0.68  (cannot learn XOR boundary)
#   rf_acc          ≈ 0.90–0.98  (easily learns XOR)
#   complexity_gap  ≥ 0.25       (strong justification for quantum kernel)
#   pca_95_count    ≤ 4          (well below 16-qubit limit)
#   rows            = 200        (fast COBYLA convergence)
# ─────────────────────────────────────────────────────────────────────────────

M = 200

# Four physically motivated features for a topological material
spin_orbit    = rng.uniform(-np.pi, np.pi, M)   # primary: spin-orbit coupling angle
crystal_field = rng.uniform(-2.0, 2.0, M)        # primary: crystal field splitting (eV)
exchange_J    = rng.uniform(-1.5, 1.5, M)         # secondary: exchange interaction
fermi_energy  = rng.uniform(-1.0, 1.0, M)         # secondary: Fermi level offset (eV)

# Phase label: XOR of primary feature signs creates a 4-quadrant checkerboard
# boundary that is provably non-linearly separable. Secondary features add
# a weak modulation so the boundary is not perfectly axis-aligned.
primary   = np.sign(spin_orbit) * np.sign(crystal_field)   # +1 or -1 per quadrant
secondary = np.sign(exchange_J * fermi_energy)              # weak interaction term
parity    = primary + 0.4 * secondary
phase_label = np.where(parity >= 0, "topological", "trivial")

# Small Gaussian noise to prevent RF from memorising exact boundaries
noise = 0.06
df_run = pd.DataFrame({
    "spin_orbit_coupling": spin_orbit    + rng.normal(0, noise, M),
    "crystal_field_eV":    crystal_field + rng.normal(0, noise, M),
    "exchange_interaction": exchange_J   + rng.normal(0, noise, M),
    "fermi_energy_eV":     fermi_energy  + rng.normal(0, noise, M),
    "phase":               phase_label,
})

df_run = df_run.sample(frac=1, random_state=42).reset_index(drop=True)
run_path = DATA_DIR / "test_dataset_run.csv"
df_run.to_csv(run_path, index=False)
print(f"Saved PROCEED dataset → {run_path}  ({len(df_run)} rows, {len(df_run.columns)-1} features)")


# ─────────────────────────────────────────────────────────────────────────────
# Quick sanity-check: run the same metrics as profiler.py
# ─────────────────────────────────────────────────────────────────────────────
from sklearn.svm import LinearSVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.decomposition import PCA

def quick_profile(df, target_col, label):
    X = df.drop(columns=[target_col])
    y = LabelEncoder().fit_transform(df[target_col])
    X_s = StandardScaler().fit_transform(X)

    lsvc = LinearSVC(C=1000, max_iter=5000)
    lsvc.fit(X_s, y)
    linear_acc = float((lsvc.predict(X_s) == y).mean())

    rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    rf.fit(X_s, y)
    rf_acc = float((rf.predict(X_s) == y).mean())

    pca = PCA(n_components=min(X_s.shape))
    pca.fit(X_s)
    pca_95 = int((pca.explained_variance_ratio_.cumsum() < 0.95).sum() + 1)

    print(f"\n── {label} ──")
    print(f"  rows            : {len(df)}")
    print(f"  features        : {X.shape[1]}")
    print(f"  linear_svc_acc  : {linear_acc:.4f}  {'⛔ ABORT' if linear_acc > 0.90 else '✓'}")
    print(f"  rf_acc          : {rf_acc:.4f}")
    print(f"  complexity_gap  : {rf_acc - linear_acc:.4f}")
    print(f"  pca_95_count    : {pca_95}         {'⛔ ABORT' if pca_95 > 16 else '✓'}")

quick_profile(df_abort, "particle_type", "ABORT dataset (particle beam)")
quick_profile(df_run,   "phase",         "PROCEED dataset (quantum materials — PoC optimised)")
