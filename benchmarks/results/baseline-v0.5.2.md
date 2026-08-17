# ScanSplitter benchmark result

Scan detector: `v4`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1.

| Suite | Cases | Box quality | Mean IoU | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|
| scansplitter | 10 | 83.7% | 0.837 | 100.0% | 58.3% | 100.0% | 6.05s |
| album | 10 | 94.7% | 0.947 | 92.3% | 92.3% | 100.0% | 11.15s |
| all | 20 | 86.6% | 0.866 | 98.0% | 67.3% | 100.0% | 17.21s |

## Per case

| Case | Expected | Found | Box quality | Mean IoU | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---|
| scansplitter-01-clean-grid | 4 | 4 | 83.0% | 0.830 | 100.0% | 50.0% | good |
| scansplitter-02-rotated-three | 3 | 3 | 84.0% | 0.840 | 100.0% | 66.7% | good |
| scansplitter-03-low-contrast | 3 | 3 | 83.0% | 0.830 | 100.0% | 0.0% | good |
| scansplitter-04-mixed-sizes | 5 | 5 | 86.6% | 0.866 | 100.0% | 80.0% | good |
| scansplitter-05-narrow-gutters | 4 | 4 | 69.1% | 0.691 | 100.0% | 0.0% | loose |
| scansplitter-06-dark-platen | 3 | 3 | 89.5% | 0.895 | 100.0% | 100.0% | good |
| scansplitter-07-portrait-and-square | 4 | 4 | 89.2% | 0.892 | 100.0% | 100.0% | good |
| scansplitter-08-edge-near | 4 | 4 | 88.9% | 0.889 | 100.0% | 100.0% | good |
| scansplitter-09-faded-pale | 3 | 3 | 83.0% | 0.830 | 100.0% | 0.0% | good |
| scansplitter-10-irregular-spacing | 3 | 3 | 80.1% | 0.801 | 100.0% | 66.7% | good |
| album-01-cream-single | 1 | 1 | 99.6% | 0.996 | 100.0% | 100.0% | excellent |
| album-02-black-single | 1 | 1 | 99.6% | 0.996 | 100.0% | 100.0% | excellent |
| album-03-wide-auto-spread | 2 | 2 | 99.5% | 0.995 | 100.0% | 100.0% | excellent |
| album-04-forced-spread | 2 | 2 | 97.4% | 0.974 | 100.0% | 100.0% | excellent |
| album-05-portrait-page | 1 | 1 | 96.2% | 0.962 | 100.0% | 100.0% | excellent |
| album-06-ivory-single | 1 | 1 | 96.4% | 0.964 | 100.0% | 100.0% | excellent |
| album-07-burgundy-page | 1 | 1 | 99.6% | 0.996 | 100.0% | 100.0% | excellent |
| album-08-small-page | 1 | 1 | 99.5% | 0.995 | 100.0% | 100.0% | excellent |
| album-09-landscape-single | 1 | 1 | 49.2% | 0.492 | 0.0% | 0.0% | poor |
| album-10-rose-auto-spread | 2 | 2 | 98.2% | 0.982 | 100.0% | 100.0% | excellent |
