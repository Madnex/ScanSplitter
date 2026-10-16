# ScanSplitter benchmark result

Scan detector: `v6`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| robust-dev | 47 | 95.9% | 97.9% | 98.8% | 99.0% | 93.9% | 97.9% | 17.03s |

## Per scenario

| Scenario | Cases | Regions | Box quality | F1@0.50 | F1@0.85 | Count accuracy |
|---|---:|---:|---:|---:|---:|---:|
| album | 4 | 20 | 92.7% | 95.0% | 85.0% | 100.0% |
| edge-touching | 4 | 9 | 98.9% | 100.0% | 100.0% | 100.0% |
| flatbed-black | 4 | 11 | 98.7% | 100.0% | 100.0% | 100.0% |
| flatbed-white | 5 | 17 | 98.6% | 100.0% | 100.0% | 100.0% |
| low-contrast | 4 | 11 | 93.2% | 100.0% | 81.8% | 100.0% |
| many-small | 3 | 30 | 96.9% | 100.0% | 100.0% | 100.0% |
| mixed-hard | 3 | 11 | 94.1% | 100.0% | 90.9% | 100.0% |
| phone-capture | 4 | 6 | 96.6% | 100.0% | 100.0% | 100.0% |
| polaroid | 4 | 6 | 94.0% | 100.0% | 83.3% | 100.0% |
| rotated | 4 | 12 | 97.6% | 100.0% | 91.7% | 100.0% |
| single-large | 4 | 4 | 99.5% | 100.0% | 100.0% | 100.0% |
| tight-gutters | 4 | 18 | 92.9% | 97.1% | 91.4% | 75.0% |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| robust-dev-flatbed-white-01 | 2 | 2 | 99.2% | 99.6% | 99.6% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-02 | 2 | 2 | 99.7% | 99.8% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-03 | 6 | 6 | 98.4% | 98.9% | 99.7% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-04 | 4 | 4 | 98.4% | 99.0% | 99.3% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-white-05 | 3 | 3 | 97.8% | 98.9% | 99.5% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-01 | 3 | 3 | 99.0% | 99.2% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-02 | 1 | 1 | 99.2% | 99.4% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-03 | 5 | 5 | 98.5% | 99.2% | 99.4% | 100.0% | 100.0% | excellent |
| robust-dev-flatbed-black-04 | 2 | 2 | 98.5% | 99.0% | 99.5% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-01 | 3 | 3 | 99.0% | 99.4% | 99.6% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-02 | 2 | 2 | 98.6% | 98.8% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-03 | 4 | 4 | 99.0% | 99.1% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-rotated-04 | 3 | 3 | 93.9% | 99.3% | 94.3% | 100.0% | 66.7% | excellent |
| robust-dev-single-large-01 | 1 | 1 | 99.8% | 99.9% | 100.0% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-02 | 1 | 1 | 99.3% | 99.6% | 99.7% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-03 | 1 | 1 | 99.5% | 99.8% | 99.7% | 100.0% | 100.0% | excellent |
| robust-dev-single-large-04 | 1 | 1 | 99.5% | 99.8% | 99.7% | 100.0% | 100.0% | excellent |
| robust-dev-many-small-01 | 12 | 12 | 97.1% | 98.2% | 99.2% | 100.0% | 100.0% | excellent |
| robust-dev-many-small-02 | 10 | 10 | 96.4% | 97.6% | 98.9% | 100.0% | 100.0% | excellent |
| robust-dev-many-small-03 | 8 | 8 | 97.2% | 97.8% | 99.5% | 100.0% | 100.0% | excellent |
| robust-dev-tight-gutters-01 | 4 | 4 | 98.1% | 98.5% | 99.6% | 100.0% | 100.0% | excellent |
| robust-dev-tight-gutters-02 | 4 | 4 | 97.6% | 97.8% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-tight-gutters-03 | 6 | 5 | 81.3% | 86.2% | 87.1% | 90.9% | 72.7% | good |
| robust-dev-tight-gutters-04 | 4 | 4 | 99.1% | 99.5% | 99.5% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-01 | 2 | 2 | 99.1% | 99.3% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-02 | 1 | 1 | 99.5% | 99.7% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-03 | 3 | 3 | 98.8% | 99.4% | 99.3% | 100.0% | 100.0% | excellent |
| robust-dev-edge-touching-04 | 3 | 3 | 98.6% | 99.3% | 99.4% | 100.0% | 100.0% | excellent |
| robust-dev-low-contrast-01 | 4 | 4 | 91.3% | 95.3% | 97.6% | 100.0% | 75.0% | excellent |
| robust-dev-low-contrast-02 | 2 | 2 | 98.8% | 99.1% | 99.6% | 100.0% | 100.0% | excellent |
| robust-dev-low-contrast-03 | 3 | 3 | 87.8% | 99.5% | 85.9% | 100.0% | 66.7% | good |
| robust-dev-low-contrast-04 | 2 | 2 | 99.4% | 99.6% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-polaroid-01 | 1 | 1 | 80.8% | 80.9% | 99.9% | 100.0% | 0.0% | good |
| robust-dev-polaroid-02 | 3 | 3 | 98.6% | 98.8% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-polaroid-03 | 1 | 1 | 94.1% | 94.2% | 99.9% | 100.0% | 100.0% | excellent |
| robust-dev-polaroid-04 | 1 | 1 | 93.6% | 93.8% | 99.7% | 100.0% | 100.0% | excellent |
| robust-dev-phone-capture-01 | 1 | 1 | 94.2% | 94.2% | 100.0% | 100.0% | 100.0% | excellent |
| robust-dev-phone-capture-02 | 3 | 3 | 95.9% | 96.4% | 99.4% | 100.0% | 100.0% | excellent |
| robust-dev-phone-capture-03 | 1 | 1 | 99.0% | 100.0% | 99.0% | 100.0% | 100.0% | excellent |
| robust-dev-phone-capture-04 | 1 | 1 | 98.5% | 99.7% | 98.8% | 100.0% | 100.0% | excellent |
| robust-dev-album-01 | 6 | 6 | 92.6% | 92.3% | 99.9% | 100.0% | 83.3% | excellent |
| robust-dev-album-02 | 6 | 6 | 98.0% | 98.3% | 99.7% | 100.0% | 100.0% | excellent |
| robust-dev-album-03 | 5 | 5 | 94.1% | 94.1% | 99.9% | 100.0% | 80.0% | excellent |
| robust-dev-album-04 | 3 | 3 | 79.8% | 99.2% | 78.8% | 66.7% | 66.7% | loose |
| robust-dev-mixed-hard-01 | 4 | 4 | 96.7% | 96.9% | 99.8% | 100.0% | 100.0% | excellent |
| robust-dev-mixed-hard-02 | 3 | 3 | 85.9% | 86.7% | 94.0% | 100.0% | 66.7% | good |
| robust-dev-mixed-hard-03 | 4 | 4 | 97.7% | 98.3% | 99.3% | 100.0% | 100.0% | excellent |
