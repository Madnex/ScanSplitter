# ScanSplitter benchmark result

Scan detector: `v6`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| robust-holdout | 47 | 93.9% | 95.9% | 98.9% | 98.1% | 92.6% | 89.4% | 16.71s |

## Per scenario

| Scenario | Cases | Regions | Box quality | F1@0.50 | F1@0.85 | Count accuracy |
|---|---:|---:|---:|---:|---:|---:|
| album | 4 | 14 | 85.0% | 89.7% | 75.9% | 75.0% |
| edge-touching | 4 | 9 | 84.1% | 94.7% | 73.7% | 75.0% |
| flatbed-black | 4 | 20 | 98.5% | 100.0% | 100.0% | 100.0% |
| flatbed-white | 5 | 26 | 97.3% | 100.0% | 100.0% | 100.0% |
| low-contrast | 4 | 6 | 98.7% | 100.0% | 100.0% | 100.0% |
| many-small | 3 | 34 | 95.1% | 100.0% | 94.1% | 100.0% |
| mixed-hard | 3 | 13 | 91.6% | 96.3% | 88.9% | 66.7% |
| phone-capture | 4 | 11 | 95.6% | 100.0% | 100.0% | 100.0% |
| polaroid | 4 | 7 | 92.4% | 100.0% | 71.4% | 100.0% |
| rotated | 4 | 15 | 97.8% | 100.0% | 100.0% | 100.0% |
| single-large | 4 | 4 | 88.5% | 88.9% | 88.9% | 75.0% |
| tight-gutters | 4 | 20 | 92.1% | 97.6% | 92.7% | 75.0% |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| robust-holdout-flatbed-white-01 | 6 | 6 | 98.1% | 99.0% | 99.2% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-white-02 | 5 | 5 | 96.1% | 97.2% | 99.3% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-white-03 | 6 | 6 | 98.3% | 98.8% | 99.5% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-white-04 | 4 | 4 | 95.7% | 96.6% | 99.6% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-white-05 | 5 | 5 | 97.9% | 98.5% | 99.4% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-black-01 | 5 | 5 | 97.8% | 99.1% | 98.8% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-black-02 | 5 | 5 | 98.6% | 99.3% | 99.6% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-black-03 | 5 | 5 | 98.7% | 99.1% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-black-04 | 5 | 5 | 98.9% | 99.3% | 99.5% | 100.0% | 100.0% | excellent |
| robust-holdout-rotated-01 | 4 | 4 | 98.7% | 99.3% | 99.5% | 100.0% | 100.0% | excellent |
| robust-holdout-rotated-02 | 3 | 3 | 99.0% | 99.0% | 99.9% | 100.0% | 100.0% | excellent |
| robust-holdout-rotated-03 | 4 | 4 | 94.9% | 96.8% | 98.3% | 100.0% | 100.0% | excellent |
| robust-holdout-rotated-04 | 4 | 4 | 98.8% | 99.3% | 99.5% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-01 | 1 | 1 | 99.5% | 99.7% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-02 | 1 | 2 | 66.4% | 92.6% | 99.8% | 66.7% | 66.7% | loose |
| robust-holdout-single-large-03 | 1 | 1 | 99.6% | 99.8% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-04 | 1 | 1 | 99.4% | 99.8% | 99.6% | 100.0% | 100.0% | excellent |
| robust-holdout-many-small-01 | 10 | 10 | 96.5% | 97.2% | 99.4% | 100.0% | 100.0% | excellent |
| robust-holdout-many-small-02 | 12 | 12 | 94.3% | 95.7% | 99.2% | 100.0% | 83.3% | excellent |
| robust-holdout-many-small-03 | 12 | 12 | 94.8% | 96.1% | 99.4% | 100.0% | 100.0% | excellent |
| robust-holdout-tight-gutters-01 | 4 | 4 | 98.1% | 98.3% | 99.7% | 100.0% | 100.0% | excellent |
| robust-holdout-tight-gutters-02 | 5 | 5 | 90.1% | 84.4% | 99.9% | 100.0% | 80.0% | excellent |
| robust-holdout-tight-gutters-03 | 5 | 6 | 86.5% | 78.4% | 100.0% | 90.9% | 90.9% | good |
| robust-holdout-tight-gutters-04 | 6 | 6 | 95.1% | 95.3% | 100.0% | 100.0% | 100.0% | excellent |
| robust-holdout-edge-touching-01 | 1 | 1 | 99.6% | 100.0% | 99.6% | 100.0% | 100.0% | excellent |
| robust-holdout-edge-touching-02 | 2 | 2 | 99.5% | 99.7% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-edge-touching-03 | 3 | 4 | 71.1% | 93.0% | 92.2% | 85.7% | 57.1% | loose |
| robust-holdout-edge-touching-04 | 3 | 3 | 83.7% | 99.2% | 84.4% | 100.0% | 66.7% | good |
| robust-holdout-low-contrast-01 | 1 | 1 | 99.7% | 99.8% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-02 | 1 | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-03 | 2 | 2 | 98.1% | 98.3% | 99.7% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-04 | 2 | 2 | 98.1% | 98.1% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-01 | 3 | 3 | 98.4% | 98.7% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-02 | 1 | 1 | 98.7% | 98.8% | 99.9% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-03 | 1 | 1 | 77.3% | 77.4% | 99.8% | 100.0% | 0.0% | loose |
| robust-holdout-polaroid-04 | 2 | 2 | 87.7% | 86.8% | 100.0% | 100.0% | 50.0% | good |
| robust-holdout-phone-capture-01 | 4 | 4 | 93.5% | 93.8% | 99.2% | 100.0% | 100.0% | excellent |
| robust-holdout-phone-capture-02 | 1 | 1 | 98.1% | 100.0% | 98.1% | 100.0% | 100.0% | excellent |
| robust-holdout-phone-capture-03 | 3 | 3 | 95.3% | 95.9% | 99.1% | 100.0% | 100.0% | excellent |
| robust-holdout-phone-capture-04 | 3 | 3 | 97.8% | 99.4% | 98.5% | 100.0% | 100.0% | excellent |
| robust-holdout-album-01 | 5 | 5 | 89.2% | 87.7% | 100.0% | 100.0% | 80.0% | good |
| robust-holdout-album-02 | 3 | 4 | 56.2% | 83.5% | 69.3% | 57.1% | 28.6% | poor |
| robust-holdout-album-03 | 4 | 4 | 97.9% | 98.0% | 99.9% | 100.0% | 100.0% | excellent |
| robust-holdout-album-04 | 2 | 2 | 98.8% | 99.4% | 99.4% | 100.0% | 100.0% | excellent |
| robust-holdout-mixed-hard-01 | 4 | 4 | 97.6% | 98.0% | 99.5% | 100.0% | 100.0% | excellent |
| robust-holdout-mixed-hard-02 | 5 | 6 | 83.4% | 92.2% | 92.3% | 90.9% | 72.7% | good |
| robust-holdout-mixed-hard-03 | 4 | 4 | 96.7% | 96.7% | 100.0% | 100.0% | 100.0% | excellent |
