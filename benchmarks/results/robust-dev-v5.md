# ScanSplitter benchmark result

Scan detector: `v5`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| robust-dev | 47 | 65.9% | 86.4% | 67.6% | 74.6% | 37.6% | 68.1% | 249.41s |

## Per scenario

| Scenario | Cases | Regions | Box quality | F1@0.50 | F1@0.85 | Count accuracy |
|---|---:|---:|---:|---:|---:|---:|
| album | 4 | 20 | 75.9% | 80.0% | 50.0% | 100.0% |
| edge-touching | 4 | 9 | 83.2% | 100.0% | 22.2% | 100.0% |
| flatbed-black | 4 | 11 | 83.0% | 95.2% | 57.1% | 75.0% |
| flatbed-white | 5 | 17 | 65.7% | 66.7% | 38.9% | 60.0% |
| low-contrast | 4 | 11 | 71.1% | 76.2% | 57.1% | 75.0% |
| many-small | 3 | 30 | 53.0% | 69.6% | 26.1% | 0.0% |
| mixed-hard | 3 | 11 | 58.6% | 63.2% | 21.1% | 66.7% |
| phone-capture | 4 | 6 | 60.2% | 83.3% | 16.7% | 50.0% |
| polaroid | 4 | 6 | 61.8% | 71.4% | 28.6% | 75.0% |
| rotated | 4 | 12 | 79.7% | 91.7% | 50.0% | 100.0% |
| single-large | 4 | 4 | 85.4% | 100.0% | 75.0% | 100.0% |
| tight-gutters | 4 | 18 | 37.5% | 35.7% | 21.4% | 0.0% |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| robust-dev-flatbed-white-01 | 2 | 3 | 55.8% | 85.8% | 66.9% | 40.0% | 40.0% | poor |
| robust-dev-flatbed-white-02 | 2 | 2 | 92.3% | 99.4% | 93.8% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-03 | 6 | 6 | 62.0% | 84.9% | 63.9% | 66.7% | 33.3% | poor |
| robust-dev-flatbed-white-04 | 4 | 4 | 78.7% | 98.4% | 77.5% | 75.0% | 50.0% | loose |
| robust-dev-flatbed-white-05 | 3 | 4 | 49.2% | 79.7% | 40.1% | 57.1% | 0.0% | poor |
| robust-dev-flatbed-black-01 | 3 | 3 | 88.4% | 95.6% | 93.1% | 100.0% | 66.7% | good |
| robust-dev-flatbed-black-02 | 1 | 1 | 95.5% | 100.0% | 95.5% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-03 | 5 | 4 | 70.8% | 100.0% | 71.1% | 88.9% | 22.2% | loose |
| robust-dev-flatbed-black-04 | 2 | 2 | 96.0% | 100.0% | 95.8% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-01 | 3 | 3 | 88.1% | 96.5% | 89.7% | 100.0% | 66.7% | good |
| robust-dev-rotated-02 | 2 | 2 | 97.1% | 98.1% | 99.1% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-03 | 4 | 4 | 67.0% | 98.6% | 66.4% | 75.0% | 25.0% | loose |
| robust-dev-rotated-04 | 3 | 3 | 76.5% | 99.7% | 74.5% | 100.0% | 33.3% | loose |
| robust-dev-single-large-01 | 1 | 1 | 96.6% | 100.0% | 96.6% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-02 | 1 | 1 | 92.3% | 93.3% | 98.9% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-03 | 1 | 1 | 61.2% | 100.0% | 61.2% | 100.0% | 0.0% | poor |
| robust-dev-single-large-04 | 1 | 1 | 91.4% | 95.9% | 95.2% | 100.0% | 100.0% | excellent |
| robust-dev-many-small-01 | 12 | 4 | 38.0% | 84.2% | 30.2% | 50.0% | 12.5% | poor |
| robust-dev-many-small-02 | 10 | 5 | 50.9% | 91.1% | 41.4% | 66.7% | 26.7% | poor |
| robust-dev-many-small-03 | 8 | 7 | 71.0% | 99.3% | 71.0% | 93.3% | 40.0% | loose |
| robust-dev-tight-gutters-01 | 4 | 2 | 47.9% | 98.7% | 39.7% | 33.3% | 33.3% | poor |
| robust-dev-tight-gutters-02 | 4 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-tight-gutters-03 | 6 | 2 | 34.6% | 96.4% | 28.6% | 25.0% | 25.0% | poor |
| robust-dev-tight-gutters-04 | 4 | 6 | 48.5% | 86.7% | 59.0% | 60.0% | 20.0% | poor |
| robust-dev-edge-touching-01 | 2 | 2 | 83.2% | 99.8% | 86.6% | 100.0% | 50.0% | good |
| robust-dev-edge-touching-02 | 1 | 1 | 79.9% | 100.0% | 79.9% | 100.0% | 0.0% | loose |
| robust-dev-edge-touching-03 | 3 | 3 | 80.6% | 100.0% | 80.8% | 100.0% | 0.0% | good |
| robust-dev-edge-touching-04 | 3 | 3 | 86.8% | 99.3% | 87.3% | 100.0% | 33.3% | good |
| robust-dev-low-contrast-01 | 4 | 4 | 88.1% | 99.8% | 88.7% | 100.0% | 75.0% | good |
| robust-dev-low-contrast-02 | 2 | 2 | 40.9% | 100.0% | 41.0% | 50.0% | 0.0% | poor |
| robust-dev-low-contrast-03 | 3 | 2 | 74.1% | 100.0% | 54.8% | 80.0% | 80.0% | loose |
| robust-dev-low-contrast-04 | 2 | 2 | 63.5% | 99.3% | 64.1% | 50.0% | 50.0% | poor |
| robust-dev-polaroid-01 | 1 | 1 | 86.8% | 100.0% | 86.8% | 100.0% | 100.0% | good |
| robust-dev-polaroid-02 | 3 | 3 | 56.5% | 25.7% | 100.0% | 66.7% | 0.0% | poor |
| robust-dev-polaroid-03 | 1 | 1 | 97.7% | 99.9% | 97.8% | 100.0% | 100.0% | excellent |
| robust-dev-polaroid-04 | 1 | 3 | 39.3% | 59.9% | 100.0% | 50.0% | 0.0% | poor |
| robust-dev-phone-capture-01 | 1 | 1 | 50.8% | 99.4% | 51.0% | 100.0% | 0.0% | poor |
| robust-dev-phone-capture-02 | 3 | 4 | 61.4% | 81.4% | 71.9% | 85.7% | 0.0% | poor |
| robust-dev-phone-capture-03 | 1 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-phone-capture-04 | 1 | 1 | 95.6% | 100.0% | 95.6% | 100.0% | 100.0% | excellent |
| robust-dev-album-01 | 6 | 6 | 80.9% | 88.8% | 87.1% | 100.0% | 50.0% | good |
| robust-dev-album-02 | 6 | 6 | 58.7% | 100.0% | 58.8% | 50.0% | 0.0% | poor |
| robust-dev-album-03 | 5 | 5 | 91.9% | 93.0% | 98.6% | 100.0% | 100.0% | excellent |
| robust-dev-album-04 | 3 | 3 | 73.5% | 100.0% | 72.0% | 66.7% | 66.7% | loose |
| robust-dev-mixed-hard-01 | 4 | 1 | 19.5% | 51.2% | 23.4% | 0.0% | 0.0% | poor |
| robust-dev-mixed-hard-02 | 3 | 3 | 66.6% | 43.5% | 96.5% | 66.7% | 66.7% | loose |
| robust-dev-mixed-hard-03 | 4 | 4 | 77.0% | 99.8% | 76.9% | 100.0% | 0.0% | loose |
