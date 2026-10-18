# ScanSplitter benchmark result

Scan detector: `v5`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| robust-holdout | 47 | 74.5% | 89.8% | 69.2% | 88.0% | 45.5% | 74.5% | 251.67s |

## Per scenario

| Scenario | Cases | Regions | Box quality | F1@0.50 | F1@0.85 | Count accuracy |
|---|---:|---:|---:|---:|---:|---:|
| album | 4 | 14 | 79.7% | 96.3% | 59.3% | 75.0% |
| edge-touching | 4 | 9 | 77.6% | 88.9% | 66.7% | 100.0% |
| flatbed-black | 4 | 20 | 82.5% | 100.0% | 50.0% | 100.0% |
| flatbed-white | 5 | 26 | 84.0% | 100.0% | 50.0% | 100.0% |
| low-contrast | 4 | 6 | 76.1% | 76.9% | 76.9% | 75.0% |
| many-small | 3 | 34 | 57.6% | 75.0% | 25.0% | 0.0% |
| mixed-hard | 3 | 13 | 88.0% | 100.0% | 46.2% | 100.0% |
| phone-capture | 4 | 11 | 79.5% | 95.7% | 43.5% | 75.0% |
| polaroid | 4 | 7 | 81.5% | 100.0% | 14.3% | 100.0% |
| rotated | 4 | 15 | 86.7% | 100.0% | 66.7% | 100.0% |
| single-large | 4 | 4 | 54.4% | 60.0% | 40.0% | 50.0% |
| tight-gutters | 4 | 20 | 50.4% | 52.9% | 29.4% | 0.0% |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| robust-holdout-flatbed-white-01 | 6 | 6 | 88.8% | 96.7% | 91.8% | 100.0% | 83.3% | good |
| robust-holdout-flatbed-white-02 | 5 | 5 | 85.0% | 90.1% | 94.9% | 100.0% | 60.0% | good |
| robust-holdout-flatbed-white-03 | 6 | 6 | 83.6% | 98.5% | 83.8% | 100.0% | 33.3% | good |
| robust-holdout-flatbed-white-04 | 4 | 4 | 89.7% | 98.0% | 92.0% | 100.0% | 75.0% | good |
| robust-holdout-flatbed-white-05 | 5 | 5 | 73.3% | 100.0% | 73.2% | 100.0% | 0.0% | loose |
| robust-holdout-flatbed-black-01 | 5 | 5 | 81.9% | 85.3% | 96.2% | 100.0% | 60.0% | good |
| robust-holdout-flatbed-black-02 | 5 | 5 | 81.2% | 99.8% | 78.5% | 100.0% | 40.0% | good |
| robust-holdout-flatbed-black-03 | 5 | 5 | 83.7% | 95.3% | 88.1% | 100.0% | 40.0% | good |
| robust-holdout-flatbed-black-04 | 5 | 5 | 83.2% | 98.8% | 83.1% | 100.0% | 60.0% | good |
| robust-holdout-rotated-01 | 4 | 4 | 89.0% | 99.2% | 87.4% | 100.0% | 50.0% | good |
| robust-holdout-rotated-02 | 3 | 3 | 91.0% | 97.1% | 93.0% | 100.0% | 100.0% | excellent |
| robust-holdout-rotated-03 | 4 | 4 | 76.7% | 99.3% | 74.5% | 100.0% | 25.0% | loose |
| robust-holdout-rotated-04 | 4 | 4 | 91.1% | 97.4% | 93.5% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-01 | 1 | 2 | 23.7% | 79.2% | 35.5% | 0.0% | 0.0% | poor |
| robust-holdout-single-large-02 | 1 | 2 | 39.3% | 88.6% | 58.9% | 66.7% | 0.0% | poor |
| robust-holdout-single-large-03 | 1 | 1 | 90.7% | 100.0% | 90.7% | 100.0% | 100.0% | excellent |
| robust-holdout-single-large-04 | 1 | 1 | 86.8% | 86.9% | 99.9% | 100.0% | 100.0% | good |
| robust-holdout-many-small-01 | 10 | 6 | 57.0% | 91.6% | 53.1% | 75.0% | 25.0% | poor |
| robust-holdout-many-small-02 | 12 | 8 | 62.8% | 98.0% | 58.3% | 80.0% | 40.0% | poor |
| robust-holdout-many-small-03 | 12 | 8 | 52.9% | 86.5% | 49.6% | 70.0% | 10.0% | poor |
| robust-holdout-tight-gutters-01 | 4 | 3 | 43.0% | 98.9% | 36.2% | 28.6% | 0.0% | poor |
| robust-holdout-tight-gutters-02 | 5 | 2 | 52.3% | 97.8% | 34.5% | 57.1% | 57.1% | poor |
| robust-holdout-tight-gutters-03 | 5 | 6 | 60.3% | 91.5% | 68.1% | 72.7% | 36.4% | poor |
| robust-holdout-tight-gutters-04 | 6 | 3 | 42.5% | 41.2% | 44.6% | 44.4% | 22.2% | poor |
| robust-holdout-edge-touching-01 | 1 | 1 | 87.7% | 100.0% | 87.7% | 100.0% | 100.0% | good |
| robust-holdout-edge-touching-02 | 2 | 2 | 86.2% | 90.7% | 94.3% | 100.0% | 100.0% | good |
| robust-holdout-edge-touching-03 | 3 | 3 | 82.0% | 98.6% | 80.3% | 100.0% | 66.7% | good |
| robust-holdout-edge-touching-04 | 3 | 3 | 64.2% | 99.7% | 66.5% | 66.7% | 33.3% | poor |
| robust-holdout-low-contrast-01 | 1 | 1 | 98.6% | 99.3% | 99.2% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-02 | 1 | 2 | 10.9% | 50.4% | 16.4% | 0.0% | 0.0% | poor |
| robust-holdout-low-contrast-03 | 2 | 2 | 98.6% | 98.6% | 100.0% | 100.0% | 100.0% | excellent |
| robust-holdout-low-contrast-04 | 2 | 2 | 91.3% | 100.0% | 91.5% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-01 | 3 | 3 | 81.9% | 85.4% | 95.5% | 100.0% | 0.0% | good |
| robust-holdout-polaroid-02 | 1 | 1 | 70.9% | 70.9% | 100.0% | 100.0% | 0.0% | loose |
| robust-holdout-polaroid-03 | 1 | 1 | 94.1% | 98.9% | 95.1% | 100.0% | 100.0% | excellent |
| robust-holdout-polaroid-04 | 2 | 2 | 79.8% | 85.6% | 92.3% | 100.0% | 0.0% | loose |
| robust-holdout-phone-capture-01 | 4 | 4 | 85.0% | 90.7% | 90.6% | 100.0% | 50.0% | good |
| robust-holdout-phone-capture-02 | 1 | 1 | 92.5% | 100.0% | 92.5% | 100.0% | 100.0% | excellent |
| robust-holdout-phone-capture-03 | 3 | 3 | 82.4% | 100.0% | 82.3% | 100.0% | 33.3% | good |
| robust-holdout-phone-capture-04 | 3 | 4 | 67.1% | 85.7% | 81.5% | 85.7% | 28.6% | loose |
| robust-holdout-album-01 | 5 | 5 | 85.8% | 96.4% | 88.7% | 100.0% | 80.0% | good |
| robust-holdout-album-02 | 3 | 2 | 59.4% | 100.0% | 56.3% | 80.0% | 40.0% | poor |
| robust-holdout-album-03 | 4 | 4 | 82.4% | 96.3% | 86.4% | 100.0% | 50.0% | good |
| robust-holdout-album-04 | 2 | 2 | 84.3% | 100.0% | 83.4% | 100.0% | 50.0% | good |
| robust-holdout-mixed-hard-01 | 4 | 4 | 87.4% | 99.5% | 88.5% | 100.0% | 25.0% | good |
| robust-holdout-mixed-hard-02 | 5 | 5 | 85.9% | 92.8% | 91.8% | 100.0% | 40.0% | good |
| robust-holdout-mixed-hard-03 | 4 | 4 | 91.3% | 99.0% | 92.3% | 100.0% | 75.0% | excellent |
