# ScanSplitter benchmark result

Scan detector: `v3`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| robust-dev | 47 | 69.7% | 84.5% | 72.4% | 79.7% | 47.1% | 68.1% | 61.53s |

## Per scenario

| Scenario | Cases | Regions | Box quality | F1@0.50 | F1@0.85 | Count accuracy |
|---|---:|---:|---:|---:|---:|---:|
| album | 4 | 20 | 58.0% | 72.7% | 24.2% | 50.0% |
| edge-touching | 4 | 9 | 87.0% | 94.1% | 94.1% | 75.0% |
| flatbed-black | 4 | 11 | 85.3% | 100.0% | 54.5% | 100.0% |
| flatbed-white | 5 | 17 | 82.7% | 97.0% | 66.7% | 80.0% |
| low-contrast | 4 | 11 | 81.9% | 95.2% | 76.2% | 75.0% |
| many-small | 3 | 30 | 72.1% | 86.8% | 18.9% | 0.0% |
| mixed-hard | 3 | 11 | 47.3% | 42.1% | 21.1% | 66.7% |
| phone-capture | 4 | 6 | 70.8% | 80.0% | 60.0% | 50.0% |
| polaroid | 4 | 6 | 49.5% | 42.9% | 42.9% | 75.0% |
| rotated | 4 | 12 | 83.0% | 91.7% | 75.0% | 100.0% |
| single-large | 4 | 4 | 88.7% | 100.0% | 75.0% | 100.0% |
| tight-gutters | 4 | 18 | 30.9% | 36.4% | 27.3% | 25.0% |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| robust-dev-flatbed-white-01 | 2 | 2 | 96.6% | 100.0% | 96.6% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-02 | 2 | 2 | 93.3% | 100.0% | 93.4% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-03 | 6 | 5 | 76.6% | 100.0% | 80.9% | 90.9% | 54.5% | loose |
| robust-dev-flatbed-white-04 | 4 | 4 | 76.7% | 100.0% | 76.1% | 100.0% | 50.0% | loose |
| robust-dev-flatbed-white-05 | 3 | 3 | 85.8% | 100.0% | 88.3% | 100.0% | 66.7% | good |
| robust-dev-flatbed-black-01 | 3 | 3 | 84.1% | 84.4% | 100.0% | 100.0% | 33.3% | good |
| robust-dev-flatbed-black-02 | 1 | 1 | 97.2% | 97.2% | 100.0% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-03 | 5 | 5 | 84.2% | 95.0% | 88.9% | 100.0% | 60.0% | good |
| robust-dev-flatbed-black-04 | 2 | 2 | 84.0% | 97.4% | 85.4% | 100.0% | 50.0% | good |
| robust-dev-rotated-01 | 3 | 3 | 79.6% | 100.0% | 80.8% | 100.0% | 66.7% | loose |
| robust-dev-rotated-02 | 2 | 2 | 93.2% | 100.0% | 93.2% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-03 | 4 | 4 | 88.5% | 98.7% | 89.7% | 100.0% | 100.0% | good |
| robust-dev-rotated-04 | 3 | 3 | 72.3% | 100.0% | 72.2% | 66.7% | 33.3% | loose |
| robust-dev-single-large-01 | 1 | 1 | 98.2% | 100.0% | 98.2% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-02 | 1 | 1 | 95.8% | 100.0% | 95.8% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-03 | 1 | 1 | 65.1% | 100.0% | 65.1% | 100.0% | 0.0% | loose |
| robust-dev-single-large-04 | 1 | 1 | 95.7% | 100.0% | 95.7% | 100.0% | 100.0% | excellent |
| robust-dev-many-small-01 | 12 | 8 | 64.2% | 100.0% | 61.8% | 80.0% | 0.0% | poor |
| robust-dev-many-small-02 | 10 | 8 | 71.9% | 100.0% | 67.6% | 88.9% | 0.0% | loose |
| robust-dev-many-small-03 | 8 | 7 | 83.0% | 97.9% | 77.0% | 93.3% | 66.7% | good |
| robust-dev-tight-gutters-01 | 4 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-tight-gutters-02 | 4 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-tight-gutters-03 | 6 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-tight-gutters-04 | 4 | 4 | 85.1% | 95.9% | 89.1% | 100.0% | 75.0% | good |
| robust-dev-edge-touching-01 | 2 | 2 | 96.4% | 95.9% | 100.0% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-02 | 1 | 1 | 97.2% | 100.0% | 97.2% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-03 | 3 | 3 | 89.5% | 100.0% | 89.8% | 100.0% | 100.0% | good |
| robust-dev-edge-touching-04 | 3 | 2 | 72.4% | 100.0% | 61.0% | 80.0% | 80.0% | loose |
| robust-dev-low-contrast-01 | 4 | 4 | 85.5% | 98.7% | 87.4% | 100.0% | 75.0% | good |
| robust-dev-low-contrast-02 | 2 | 2 | 73.7% | 100.0% | 73.5% | 100.0% | 50.0% | loose |
| robust-dev-low-contrast-03 | 3 | 2 | 73.9% | 98.1% | 56.7% | 80.0% | 80.0% | loose |
| robust-dev-low-contrast-04 | 2 | 2 | 92.8% | 99.2% | 93.5% | 100.0% | 100.0% | excellent |
| robust-dev-polaroid-01 | 1 | 1 | 86.1% | 94.6% | 90.5% | 100.0% | 100.0% | good |
| robust-dev-polaroid-02 | 3 | 3 | 28.6% | 26.5% | 100.0% | 0.0% | 0.0% | poor |
| robust-dev-polaroid-03 | 1 | 1 | 87.6% | 89.2% | 98.0% | 100.0% | 100.0% | good |
| robust-dev-polaroid-04 | 1 | 3 | 43.7% | 66.7% | 98.1% | 50.0% | 50.0% | poor |
| robust-dev-phone-capture-01 | 1 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-phone-capture-02 | 3 | 3 | 87.5% | 95.3% | 91.8% | 100.0% | 66.7% | good |
| robust-dev-phone-capture-03 | 1 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-phone-capture-04 | 1 | 1 | 91.5% | 95.6% | 95.6% | 100.0% | 100.0% | excellent |
| robust-dev-album-01 | 6 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-album-02 | 6 | 5 | 63.8% | 98.9% | 59.9% | 90.9% | 18.2% | poor |
| robust-dev-album-03 | 5 | 5 | 79.4% | 85.6% | 91.6% | 100.0% | 20.0% | loose |
| robust-dev-album-04 | 3 | 3 | 69.9% | 100.0% | 68.3% | 66.7% | 66.7% | loose |
| robust-dev-mixed-hard-01 | 4 | 1 | 10.2% | 25.8% | 25.4% | 0.0% | 0.0% | poor |
| robust-dev-mixed-hard-02 | 3 | 3 | 32.8% | 31.4% | 99.8% | 0.0% | 0.0% | poor |
| robust-dev-mixed-hard-03 | 4 | 4 | 81.2% | 96.0% | 83.8% | 100.0% | 50.0% | good |
