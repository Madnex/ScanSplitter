# ScanSplitter benchmark result

Scan detector: `openrouter` using `google/gemini-3.7-flash`. Detection F1 uses IoU `0.50`; strict F1 uses IoU `0.85`. Box quality is IoU-weighted F1. Tightness is wanted image area divided by detected crop area; coverage is wanted image area retained.

| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| scansplitter | 10 | 93.8% | 94.1% | 99.7% | 100.0% | 96.3% | 100.0% | 104.06s |

## Per case

| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| scansplitter-01-aged-album-spread | 6 | 6 | 94.5% | 94.7% | 99.9% | 100.0% | 100.0% | excellent |
| scansplitter-02-wide-paper-margins | 5 | 5 | 94.4% | 94.4% | 99.7% | 100.0% | 100.0% | excellent |
| scansplitter-03-tape-and-photo-corners | 5 | 5 | 92.0% | 92.4% | 99.8% | 100.0% | 100.0% | excellent |
| scansplitter-04-scalloped-low-contrast | 5 | 5 | 94.8% | 95.1% | 99.9% | 100.0% | 100.0% | excellent |
| scansplitter-05-narrow-mounted-gutters | 6 | 6 | 96.8% | 96.9% | 99.9% | 100.0% | 100.0% | excellent |
| scansplitter-06-dark-scrapbook-page | 5 | 5 | 92.1% | 92.8% | 99.5% | 100.0% | 100.0% | excellent |
| scansplitter-07-mixed-print-formats | 6 | 6 | 93.9% | 93.9% | 100.0% | 100.0% | 100.0% | excellent |
| scansplitter-08-page-edge-and-binding | 6 | 6 | 91.7% | 92.5% | 99.4% | 100.0% | 83.3% | excellent |
| scansplitter-09-faded-glossy-protection | 5 | 5 | 97.0% | 96.9% | 99.9% | 100.0% | 100.0% | excellent |
| scansplitter-10-irregular-real-world-layout | 5 | 5 | 91.0% | 92.0% | 99.5% | 100.0% | 80.0% | excellent |
