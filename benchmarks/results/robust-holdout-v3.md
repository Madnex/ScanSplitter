# ScanSplitter benchmark result

Scan detector: `v3`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| robust-holdout | 47 | 73.0% | 84.3% | 63.7% | 85.7% | 43.8% | 57.4% | 3.90s |

## Per scenario

| Scenario | Cases | Regions | Box quality | F1@0.50 | F1@0.85 | Count accuracy |
|---|---:|---:|---:|---:|---:|---:|
| album | 4 | 14 | 80.1% | 96.3% | 59.3% | 75.0% |
| edge-touching | 4 | 9 | 77.3% | 82.4% | 70.6% | 75.0% |
| flatbed-black | 4 | 20 | 75.9% | 88.9% | 55.6% | 25.0% |
| flatbed-white | 5 | 26 | 82.1% | 94.1% | 51.0% | 80.0% |
| low-contrast | 4 | 6 | 52.9% | 54.5% | 54.5% | 50.0% |
| many-small | 3 | 34 | 68.3% | 84.7% | 10.2% | 0.0% |
| mixed-hard | 3 | 13 | 80.1% | 96.0% | 56.0% | 66.7% |
| phone-capture | 4 | 11 | 79.3% | 95.2% | 57.1% | 75.0% |
| polaroid | 4 | 7 | 81.7% | 100.0% | 28.6% | 100.0% |
| rotated | 4 | 15 | 82.3% | 96.6% | 62.1% | 75.0% |
| single-large | 4 | 4 | 57.9% | 60.0% | 40.0% | 50.0% |
| tight-gutters | 4 | 20 | 42.7% | 48.3% | 20.7% | 0.0% |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| robust-holdout-flatbed-white-01 | 6 | 6 | 81.1% | 99.1% | 82.8% | 83.3% | 66.7% | good |
| robust-holdout-flatbed-white-02 | 5 | 4 | 70.7% | 100.0% | 69.9% | 88.9% | 22.2% | loose |
| robust-holdout-flatbed-white-03 | 6 | 6 | 85.4% | 100.0% | 85.6% | 100.0% | 50.0% | good |
| robust-holdout-flatbed-white-04 | 4 | 4 | 87.6% | 100.0% | 88.1% | 100.0% | 75.0% | good |
| robust-holdout-flatbed-white-05 | 5 | 5 | 85.0% | 100.0% | 85.0% | 100.0% | 40.0% | good |
| robust-holdout-flatbed-black-01 | 5 | 3 | 57.6% | 85.8% | 62.8% | 75.0% | 25.0% | poor |
| robust-holdout-flatbed-black-02 | 5 | 5 | 88.3% | 99.8% | 89.8% | 100.0% | 80.0% | good |
| robust-holdout-flatbed-black-03 | 5 | 4 | 74.8% | 93.1% | 73.4% | 88.9% | 22.2% | loose |
| robust-holdout-flatbed-black-04 | 5 | 4 | 79.5% | 95.5% | 77.2% | 88.9% | 88.9% | loose |
| robust-holdout-rotated-01 | 4 | 3 | 74.2% | 94.7% | 73.2% | 85.7% | 57.1% | loose |
| robust-holdout-rotated-02 | 3 | 3 | 86.8% | 100.0% | 84.9% | 100.0% | 66.7% | good |
| robust-holdout-rotated-03 | 4 | 4 | 81.9% | 98.6% | 79.6% | 100.0% | 50.0% | good |
| robust-holdout-rotated-04 | 4 | 4 | 86.4% | 93.7% | 92.4% | 100.0% | 75.0% | good |
| robust-holdout-single-large-01 | 1 | 2 | 25.4% | 79.4% | 38.1% | 0.0% | 0.0% | poor |
| robust-holdout-single-large-02 | 1 | 2 | 40.1% | 89.3% | 60.1% | 66.7% | 0.0% | poor |
| robust-holdout-single-large-03 | 1 | 1 | 95.6% | 100.0% | 95.6% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-04 | 1 | 1 | 95.7% | 100.0% | 95.7% | 100.0% | 100.0% | excellent |
| robust-holdout-many-small-01 | 10 | 7 | 63.2% | 100.0% | 56.0% | 82.4% | 0.0% | poor |
| robust-holdout-many-small-02 | 12 | 9 | 70.1% | 100.0% | 66.0% | 85.7% | 9.5% | loose |
| robust-holdout-many-small-03 | 12 | 9 | 70.6% | 100.0% | 68.0% | 85.7% | 19.0% | loose |
| robust-holdout-tight-gutters-01 | 4 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-holdout-tight-gutters-02 | 5 | 2 | 22.4% | 32.9% | 36.4% | 28.6% | 0.0% | poor |
| robust-holdout-tight-gutters-03 | 5 | 4 | 75.4% | 97.4% | 71.5% | 88.9% | 44.4% | loose |
| robust-holdout-tight-gutters-04 | 6 | 3 | 44.8% | 45.7% | 46.4% | 44.4% | 22.2% | poor |
| robust-holdout-edge-touching-01 | 1 | 1 | 94.0% | 100.0% | 94.0% | 100.0% | 100.0% | excellent |
| robust-holdout-edge-touching-02 | 2 | 1 | 62.4% | 100.0% | 41.4% | 66.7% | 66.7% | poor |
| robust-holdout-edge-touching-03 | 3 | 3 | 62.4% | 100.0% | 57.8% | 66.7% | 33.3% | poor |
| robust-holdout-edge-touching-04 | 3 | 3 | 94.0% | 98.7% | 96.6% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-01 | 1 | 1 | 94.2% | 98.0% | 96.0% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-02 | 1 | 2 | 10.1% | 51.2% | 15.1% | 0.0% | 0.0% | poor |
| robust-holdout-low-contrast-03 | 2 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-holdout-low-contrast-04 | 2 | 2 | 90.8% | 99.7% | 91.2% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-01 | 3 | 3 | 77.7% | 78.7% | 98.9% | 100.0% | 0.0% | loose |
| robust-holdout-polaroid-02 | 1 | 1 | 86.2% | 87.1% | 98.8% | 100.0% | 100.0% | good |
| robust-holdout-polaroid-03 | 1 | 1 | 92.9% | 100.0% | 92.9% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-04 | 2 | 2 | 79.7% | 79.7% | 100.0% | 100.0% | 0.0% | loose |
| robust-holdout-phone-capture-01 | 4 | 3 | 62.3% | 97.6% | 52.8% | 85.7% | 0.0% | poor |
| robust-holdout-phone-capture-02 | 1 | 1 | 91.9% | 100.0% | 91.9% | 100.0% | 100.0% | excellent |
| robust-holdout-phone-capture-03 | 3 | 3 | 88.5% | 96.6% | 91.4% | 100.0% | 100.0% | good |
| robust-holdout-phone-capture-04 | 3 | 3 | 85.8% | 100.0% | 87.2% | 100.0% | 66.7% | good |
| robust-holdout-album-01 | 5 | 5 | 80.0% | 86.8% | 90.5% | 100.0% | 20.0% | loose |
| robust-holdout-album-02 | 3 | 2 | 57.0% | 96.1% | 55.6% | 80.0% | 40.0% | poor |
| robust-holdout-album-03 | 4 | 4 | 88.7% | 100.0% | 88.8% | 100.0% | 100.0% | good |
| robust-holdout-album-04 | 2 | 2 | 92.3% | 100.0% | 92.3% | 100.0% | 100.0% | excellent |
| robust-holdout-mixed-hard-01 | 4 | 3 | 76.9% | 96.5% | 65.2% | 85.7% | 85.7% | loose |
| robust-holdout-mixed-hard-02 | 5 | 5 | 77.3% | 85.7% | 87.5% | 100.0% | 20.0% | loose |
| robust-holdout-mixed-hard-03 | 4 | 4 | 86.5% | 93.1% | 93.3% | 100.0% | 75.0% | good |
