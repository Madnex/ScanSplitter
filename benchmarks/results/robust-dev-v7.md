# ScanSplitter benchmark result

Scan detector: `v7`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| robust-dev | 47 | 83.4% | 90.7% | 79.2% | 86.7% | 76.9% | 76.6% | 28.78s |

## Per scenario

| Scenario | Cases | Regions | Box quality | F1@0.50 | F1@0.85 | Count accuracy |
|---|---:|---:|---:|---:|---:|---:|
| album | 4 | 20 | 88.2% | 94.7% | 78.9% | 50.0% |
| edge-touching | 4 | 9 | 99.1% | 100.0% | 100.0% | 100.0% |
| flatbed-black | 4 | 11 | 98.5% | 100.0% | 100.0% | 100.0% |
| flatbed-white | 5 | 17 | 93.6% | 100.0% | 88.2% | 100.0% |
| low-contrast | 4 | 11 | 84.3% | 90.0% | 80.0% | 75.0% |
| many-small | 3 | 30 | 83.8% | 87.3% | 83.6% | 33.3% |
| mixed-hard | 3 | 11 | 52.1% | 44.4% | 33.3% | 33.3% |
| phone-capture | 4 | 6 | 77.6% | 90.9% | 54.5% | 75.0% |
| polaroid | 4 | 6 | 78.4% | 83.3% | 50.0% | 100.0% |
| rotated | 4 | 12 | 94.7% | 100.0% | 91.7% | 100.0% |
| single-large | 4 | 4 | 92.0% | 100.0% | 75.0% | 100.0% |
| tight-gutters | 4 | 18 | 51.5% | 46.2% | 46.2% | 25.0% |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| robust-dev-flatbed-white-01 | 2 | 2 | 99.7% | 99.8% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-02 | 2 | 2 | 99.1% | 99.3% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-03 | 6 | 6 | 91.7% | 96.0% | 99.2% | 100.0% | 83.3% | excellent |
| robust-dev-flatbed-white-04 | 4 | 4 | 89.3% | 98.5% | 89.2% | 100.0% | 75.0% | good |
| robust-dev-flatbed-white-05 | 3 | 3 | 95.4% | 99.5% | 98.3% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-01 | 3 | 3 | 98.8% | 98.8% | 100.0% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-02 | 1 | 1 | 98.9% | 98.9% | 100.0% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-03 | 5 | 5 | 98.5% | 99.8% | 98.9% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-04 | 2 | 2 | 98.1% | 99.0% | 99.2% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-01 | 3 | 3 | 97.9% | 98.8% | 99.3% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-02 | 2 | 2 | 98.5% | 98.7% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-03 | 4 | 4 | 98.7% | 98.8% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-04 | 3 | 3 | 83.4% | 99.4% | 83.6% | 100.0% | 66.7% | good |
| robust-dev-single-large-01 | 1 | 1 | 99.6% | 99.8% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-02 | 1 | 1 | 99.8% | 99.9% | 100.0% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-03 | 1 | 1 | 68.9% | 99.9% | 69.0% | 100.0% | 0.0% | loose |
| robust-dev-single-large-04 | 1 | 1 | 99.7% | 99.9% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-many-small-01 | 12 | 10 | 88.9% | 98.8% | 90.0% | 90.9% | 90.9% | good |
| robust-dev-many-small-02 | 10 | 7 | 80.7% | 98.5% | 70.2% | 82.4% | 82.4% | good |
| robust-dev-many-small-03 | 8 | 8 | 80.0% | 90.8% | 86.9% | 87.5% | 75.0% | loose |
| robust-dev-tight-gutters-01 | 4 | 2 | 47.9% | 98.7% | 39.7% | 33.3% | 33.3% | poor |
| robust-dev-tight-gutters-02 | 4 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-tight-gutters-03 | 6 | 2 | 34.6% | 96.4% | 28.6% | 25.0% | 25.0% | poor |
| robust-dev-tight-gutters-04 | 4 | 4 | 96.7% | 97.0% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-01 | 2 | 2 | 98.6% | 99.3% | 99.2% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-02 | 1 | 1 | 99.5% | 99.7% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-03 | 3 | 3 | 99.4% | 99.7% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-04 | 3 | 3 | 99.0% | 99.2% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-low-contrast-01 | 4 | 4 | 97.9% | 99.0% | 99.3% | 100.0% | 100.0% | excellent |
| robust-dev-low-contrast-02 | 2 | 2 | 77.4% | 99.9% | 77.4% | 100.0% | 50.0% | loose |
| robust-dev-low-contrast-03 | 3 | 1 | 49.4% | 98.9% | 39.1% | 50.0% | 50.0% | poor |
| robust-dev-low-contrast-04 | 2 | 2 | 99.1% | 99.3% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-polaroid-01 | 1 | 1 | 86.8% | 100.0% | 86.8% | 100.0% | 100.0% | good |
| robust-dev-polaroid-02 | 3 | 3 | 62.0% | 46.8% | 100.0% | 66.7% | 0.0% | poor |
| robust-dev-polaroid-03 | 1 | 1 | 99.1% | 99.2% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-polaroid-04 | 1 | 1 | 98.6% | 98.7% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-phone-capture-01 | 1 | 1 | 50.8% | 99.4% | 51.0% | 100.0% | 0.0% | poor |
| robust-dev-phone-capture-02 | 3 | 3 | 92.9% | 98.9% | 92.3% | 100.0% | 66.7% | excellent |
| robust-dev-phone-capture-03 | 1 | 0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | poor |
| robust-dev-phone-capture-04 | 1 | 1 | 97.3% | 99.7% | 97.6% | 100.0% | 100.0% | excellent |
| robust-dev-album-01 | 6 | 6 | 84.1% | 94.7% | 87.1% | 100.0% | 50.0% | good |
| robust-dev-album-02 | 6 | 5 | 89.5% | 98.7% | 84.6% | 90.9% | 90.9% | good |
| robust-dev-album-03 | 5 | 5 | 96.5% | 97.8% | 98.6% | 100.0% | 100.0% | excellent |
| robust-dev-album-04 | 3 | 2 | 78.5% | 99.9% | 62.3% | 80.0% | 80.0% | loose |
| robust-dev-mixed-hard-01 | 4 | 1 | 10.3% | 25.8% | 26.5% | 0.0% | 0.0% | poor |
| robust-dev-mixed-hard-02 | 3 | 3 | 55.1% | 37.0% | 99.9% | 33.3% | 33.3% | poor |
| robust-dev-mixed-hard-03 | 4 | 3 | 79.4% | 97.8% | 70.2% | 85.7% | 57.1% | loose |
