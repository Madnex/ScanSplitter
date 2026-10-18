# ScanSplitter benchmark result

Scan detector: `v7`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| robust-holdout | 47 | 88.8% | 92.2% | 75.4% | 92.5% | 82.7% | 74.5% | 36.40s |

## Per scenario

| Scenario | Cases | Regions | Box quality | F1@0.50 | F1@0.85 | Count accuracy |
|---|---:|---:|---:|---:|---:|---:|
| album | 4 | 14 | 86.7% | 92.3% | 84.6% | 50.0% |
| edge-touching | 4 | 9 | 88.8% | 94.1% | 82.4% | 75.0% |
| flatbed-black | 4 | 20 | 94.4% | 100.0% | 90.0% | 100.0% |
| flatbed-white | 5 | 26 | 98.1% | 100.0% | 100.0% | 100.0% |
| low-contrast | 4 | 6 | 68.7% | 66.7% | 66.7% | 50.0% |
| many-small | 3 | 34 | 94.4% | 97.0% | 93.9% | 33.3% |
| mixed-hard | 3 | 13 | 95.5% | 100.0% | 92.3% | 100.0% |
| phone-capture | 4 | 11 | 96.9% | 100.0% | 100.0% | 100.0% |
| polaroid | 4 | 7 | 84.6% | 100.0% | 28.6% | 100.0% |
| rotated | 4 | 15 | 93.3% | 96.6% | 89.7% | 75.0% |
| single-large | 4 | 4 | 75.1% | 66.7% | 66.7% | 75.0% |
| tight-gutters | 4 | 20 | 56.5% | 60.6% | 30.3% | 25.0% |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| robust-holdout-flatbed-white-01 | 6 | 6 | 98.2% | 99.5% | 99.0% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-white-02 | 5 | 5 | 97.2% | 97.9% | 99.4% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-white-03 | 6 | 6 | 97.9% | 98.8% | 99.2% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-white-04 | 4 | 4 | 98.5% | 99.2% | 99.3% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-white-05 | 5 | 5 | 98.6% | 99.3% | 99.3% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-black-01 | 5 | 5 | 82.3% | 89.8% | 91.1% | 100.0% | 60.0% | good |
| robust-holdout-flatbed-black-02 | 5 | 5 | 98.6% | 99.6% | 99.3% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-black-03 | 5 | 5 | 98.1% | 99.0% | 99.2% | 100.0% | 100.0% | excellent |
| robust-holdout-flatbed-black-04 | 5 | 5 | 98.7% | 98.9% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-rotated-01 | 4 | 4 | 98.5% | 98.9% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-rotated-02 | 3 | 3 | 92.0% | 99.4% | 90.6% | 100.0% | 66.7% | excellent |
| robust-holdout-rotated-03 | 4 | 3 | 84.1% | 98.1% | 71.9% | 85.7% | 85.7% | good |
| robust-holdout-rotated-04 | 4 | 4 | 97.2% | 98.8% | 98.6% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-01 | 1 | 2 | 26.2% | 78.9% | 39.3% | 0.0% | 0.0% | poor |
| robust-holdout-single-large-02 | 1 | 1 | 99.8% | 99.8% | 100.0% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-03 | 1 | 1 | 99.8% | 99.9% | 99.9% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-04 | 1 | 1 | 99.2% | 99.3% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-many-small-01 | 10 | 9 | 90.3% | 96.8% | 92.2% | 94.7% | 84.2% | excellent |
| robust-holdout-many-small-02 | 12 | 11 | 93.3% | 98.5% | 94.3% | 95.7% | 95.7% | excellent |
| robust-holdout-many-small-03 | 12 | 12 | 98.5% | 99.1% | 99.5% | 100.0% | 100.0% | excellent |
| robust-holdout-tight-gutters-01 | 4 | 3 | 42.7% | 98.2% | 36.0% | 28.6% | 0.0% | poor |
| robust-holdout-tight-gutters-02 | 5 | 2 | 42.2% | 72.1% | 36.3% | 57.1% | 28.6% | poor |
| robust-holdout-tight-gutters-03 | 5 | 5 | 87.8% | 96.8% | 89.9% | 100.0% | 60.0% | good |
| robust-holdout-tight-gutters-04 | 6 | 3 | 43.8% | 44.1% | 46.9% | 44.4% | 22.2% | poor |
| robust-holdout-edge-touching-01 | 1 | 1 | 99.7% | 99.8% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-edge-touching-02 | 2 | 1 | 66.0% | 99.0% | 55.8% | 66.7% | 66.7% | loose |
| robust-holdout-edge-touching-03 | 3 | 3 | 87.1% | 98.9% | 86.2% | 100.0% | 66.7% | good |
| robust-holdout-edge-touching-04 | 3 | 3 | 98.4% | 98.3% | 99.9% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-01 | 1 | 1 | 98.6% | 99.3% | 99.2% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-02 | 1 | 2 | 10.9% | 55.4% | 16.3% | 0.0% | 0.0% | poor |
| robust-holdout-low-contrast-03 | 2 | 1 | 66.0% | 99.0% | 57.0% | 66.7% | 66.7% | loose |
| robust-holdout-low-contrast-04 | 2 | 2 | 99.2% | 99.2% | 100.0% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-01 | 3 | 3 | 78.9% | 79.1% | 100.0% | 100.0% | 0.0% | loose |
| robust-holdout-polaroid-02 | 1 | 1 | 99.0% | 99.0% | 100.0% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-03 | 1 | 1 | 99.6% | 99.8% | 99.8% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-04 | 2 | 2 | 78.3% | 78.3% | 100.0% | 100.0% | 0.0% | loose |
| robust-holdout-phone-capture-01 | 4 | 4 | 96.0% | 99.1% | 97.0% | 100.0% | 100.0% | excellent |
| robust-holdout-phone-capture-02 | 1 | 1 | 98.0% | 99.9% | 98.2% | 100.0% | 100.0% | excellent |
| robust-holdout-phone-capture-03 | 3 | 3 | 97.6% | 99.4% | 98.2% | 100.0% | 100.0% | excellent |
| robust-holdout-phone-capture-04 | 3 | 3 | 97.1% | 99.6% | 97.5% | 100.0% | 100.0% | excellent |
| robust-holdout-album-01 | 5 | 5 | 88.5% | 86.7% | 99.9% | 100.0% | 80.0% | good |
| robust-holdout-album-02 | 3 | 2 | 79.4% | 99.6% | 74.5% | 80.0% | 80.0% | loose |
| robust-holdout-album-03 | 4 | 3 | 81.9% | 97.8% | 67.2% | 85.7% | 85.7% | good |
| robust-holdout-album-04 | 2 | 2 | 99.4% | 99.8% | 99.5% | 100.0% | 100.0% | excellent |
| robust-holdout-mixed-hard-01 | 4 | 4 | 99.0% | 99.1% | 99.9% | 100.0% | 100.0% | excellent |
| robust-holdout-mixed-hard-02 | 5 | 5 | 95.1% | 99.2% | 95.2% | 100.0% | 100.0% | excellent |
| robust-holdout-mixed-hard-03 | 4 | 4 | 92.5% | 93.4% | 98.9% | 100.0% | 75.0% | excellent |
