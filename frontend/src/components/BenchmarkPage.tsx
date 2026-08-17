import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, RefreshCw } from "lucide-react";

interface BenchmarkBox {
  id: string;
  center_x: number;
  center_y: number;
  width: number;
  height: number;
  angle: number;
}

interface BenchmarkCase {
  id: string;
  suite: "scansplitter" | "album";
  layout: "auto" | "single" | "spread" | null;
  target: "photographic_content" | null;
  image_url: string;
  ground_truth: BenchmarkBox[];
}

interface Metrics {
  expected: number;
  detected: number;
  precision: number;
  recall: number;
  f1: number;
  strict_precision: number;
  strict_recall: number;
  strict_f1: number;
  box_quality: number;
  crop_tightness: number;
  content_coverage: number;
  iou_sum: number;
  intersection_area_sum: number;
  expected_area_sum: number;
  actual_area_sum: number;
  mean_iou: number;
  worst_iou: number;
  false_positive: number;
  false_negative: number;
}

interface Variant {
  key: "v3" | "v4" | "v5" | "llm" | "album";
  label: string;
  boxes: BenchmarkBox[];
  metrics: Metrics;
}

interface BenchmarkIndex {
  image_width: number;
  image_height: number;
  openrouter_enabled: boolean;
  openrouter_model: string | null;
  cases: BenchmarkCase[];
}

const COLORS: Record<string, string> = {
  truth: "#22c55e",
  v3: "#f59e0b",
  v4: "#3b82f6",
  v5: "#ef4444",
  llm: "#06b6d4",
  album: "#a855f7",
};

function ImagePanel({
  benchmarkCase,
  title,
  boxes = [],
  color = "#64748b",
  metrics,
  imageWidth,
  imageHeight,
}: {
  benchmarkCase: BenchmarkCase;
  title: string;
  boxes?: BenchmarkBox[];
  color?: string;
  metrics?: Metrics;
  imageWidth: number;
  imageHeight: number;
}) {
  return (
    <figure className="min-w-[280px] overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className="relative overflow-hidden bg-black/5" style={{ aspectRatio: `${imageWidth} / ${imageHeight}` }}>
        <img
          src={benchmarkCase.image_url}
          alt={`${benchmarkCase.id}, ${title}`}
          className="absolute inset-0 h-full w-full object-contain"
        />
        {boxes.length > 0 && (
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox={`0 0 ${imageWidth} ${imageHeight}`}
            preserveAspectRatio="xMidYMid meet"
            aria-hidden="true"
          >
            {boxes.map((box, index) => (
              <g key={box.id} transform={`rotate(${box.angle} ${box.center_x} ${box.center_y})`}>
                <rect
                  x={box.center_x - box.width / 2}
                  y={box.center_y - box.height / 2}
                  width={box.width}
                  height={box.height}
                  fill={`${color}20`}
                  stroke={color}
                  strokeWidth="7"
                  vectorEffect="non-scaling-stroke"
                />
                <circle cx={box.center_x} cy={box.center_y} r="19" fill={color} />
                <text
                  x={box.center_x}
                  y={box.center_y + 7}
                  textAnchor="middle"
                  fill="white"
                  fontSize="22"
                  fontWeight="700"
                >
                  {index + 1}
                </text>
              </g>
            ))}
          </svg>
        )}
      </div>
      <figcaption className="flex items-center justify-between gap-3 px-3 py-2.5">
        <span className="text-sm font-semibold">{title}</span>
        {metrics ? (
          <span className="text-xs tabular-nums text-muted-foreground">
            Q {(metrics.box_quality * 100).toFixed(0)}% · Tight {(metrics.crop_tightness * 100).toFixed(0)}% · Cover {(metrics.content_coverage * 100).toFixed(0)}% · {metrics.detected}/{metrics.expected}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">{boxes.length ? `${boxes.length} regions` : "source"}</span>
        )}
      </figcaption>
    </figure>
  );
}

function CaseRow({
  benchmarkCase,
  variants,
  loading,
  imageWidth,
  imageHeight,
}: {
  benchmarkCase: BenchmarkCase;
  variants?: Variant[];
  loading: boolean;
  imageWidth: number;
  imageHeight: number;
}) {
  return (
    <section className="border-t py-7 first:border-t-0">
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">{benchmarkCase.id}</h2>
          <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
            {benchmarkCase.suite === "album" ? `Album · ${benchmarkCase.layout}` : "ScanSplitter · inner photo content"}
          </p>
        </div>
        {loading && <span className="text-sm text-muted-foreground">Detecting…</span>}
      </div>
      <div className="grid grid-flow-col auto-cols-[minmax(280px,1fr)] gap-4 overflow-x-auto pb-2">
        <ImagePanel benchmarkCase={benchmarkCase} title="Original" imageWidth={imageWidth} imageHeight={imageHeight} />
        <ImagePanel
          benchmarkCase={benchmarkCase}
          title="Ground truth"
          boxes={benchmarkCase.ground_truth}
          color={COLORS.truth}
          imageWidth={imageWidth}
          imageHeight={imageHeight}
        />
        {variants?.map((variant) => (
          <ImagePanel
            key={variant.key}
            benchmarkCase={benchmarkCase}
            title={variant.label}
            boxes={variant.boxes}
            color={COLORS[variant.key]}
            metrics={variant.metrics}
            imageWidth={imageWidth}
            imageHeight={imageHeight}
          />
        ))}
      </div>
    </section>
  );
}

export function BenchmarkPage() {
  const [index, setIndex] = useState<BenchmarkIndex | null>(null);
  const [results, setResults] = useState<Record<string, Variant[]>>({});
  const [activeCase, setActiveCase] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runNumber, setRunNumber] = useState(1);

  const runBenchmark = useCallback(() => {
    setResults({});
    setError(null);
    setRunNumber((value) => value + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/benchmark", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(response.status === 404 ? "Benchmark mode is disabled." : "Could not load benchmark cases.");
        return response.json() as Promise<BenchmarkIndex>;
      })
      .then(setIndex)
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Could not load benchmark cases.");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!index) return;
    const cases = index.cases;
    const controller = new AbortController();
    let cancelled = false;
    async function run() {
      for (const benchmarkCase of cases) {
        if (cancelled) return;
        setActiveCase(benchmarkCase.id);
        const response = await fetch(`/api/benchmark/${benchmarkCase.id}/detections`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Detection failed for ${benchmarkCase.id}.`);
        const data = (await response.json()) as { variants: Variant[] };
        setResults((current) => ({ ...current, [benchmarkCase.id]: data.variants }));
      }
      setActiveCase(null);
    }
    run().catch((reason: unknown) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(reason instanceof Error ? reason.message : "Benchmark run failed.");
        setActiveCase(null);
      }
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [index, runNumber]);

  const completed = Object.keys(results).length;
  const summary = useMemo(() => {
    const grouped = new Map<Variant["key"], Variant[]>();
    for (const variant of Object.values(results).flat()) {
      grouped.set(variant.key, [...(grouped.get(variant.key) ?? []), variant]);
    }
    return Array.from(grouped.entries()).map(([key, variants]) => {
      const total = (metric: "expected" | "detected" | "iou_sum" | "intersection_area_sum" | "expected_area_sum" | "actual_area_sum") =>
        variants.reduce((sum, variant) => sum + variant.metrics[metric], 0);
      const expected = total("expected");
      const detected = total("detected");
      const intersection = total("intersection_area_sum");
      const expectedArea = total("expected_area_sum");
      const actualArea = total("actual_area_sum");
      return {
        key,
        label: key === "album" ? "Album Splitter" : variants[0].label,
        quality: expected + detected ? (2 * total("iou_sum")) / (expected + detected) : 1,
        tightness: actualArea ? intersection / actualArea : expectedArea ? 0 : 1,
        coverage: expectedArea ? intersection / expectedArea : actualArea ? 0 : 1,
      };
    });
  }, [results]);

  return (
    <main className="min-h-screen bg-muted/30">
      <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-6 px-6 py-4">
          <div className="flex items-center gap-4">
            <a href="/" className="rounded-lg p-2 hover:bg-muted" aria-label="Back to ScanSplitter"><ArrowLeft className="h-4 w-4" /></a>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Detector benchmark</h1>
              <p className="text-sm text-muted-foreground">Live visual comparison against fixed ground truth</p>
              {index && !index.openrouter_enabled && (
                <p className="text-xs text-amber-700 dark:text-amber-300">Set OPENROUTER_API_KEY to add the LLM comparison.</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            {index && <span className="text-muted-foreground">{completed}/{index.cases.length} cases</span>}
            {summary.map((item) => (
              <span key={item.key} className="hidden items-center gap-1.5 text-xs tabular-nums text-muted-foreground xl:flex">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[item.key] }} />
                {item.label}: Q {(item.quality * 100).toFixed(0)} · T {(item.tightness * 100).toFixed(0)} · C {(item.coverage * 100).toFixed(0)}
              </span>
            ))}
            <button type="button" onClick={runBenchmark} disabled={!index || activeCase !== null} className="inline-flex items-center gap-2 rounded-lg border bg-background px-3 py-2 font-medium hover:bg-muted disabled:opacity-50">
              <RefreshCw className={`h-4 w-4 ${activeCase ? "animate-spin" : ""}`} /> Run again
            </button>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-[1800px] px-6 py-5">
        {error && <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">{error}</div>}
        {!index && !error && <p className="py-20 text-center text-muted-foreground">Loading benchmark…</p>}
        {index?.cases.map((benchmarkCase) => (
          <CaseRow
            key={benchmarkCase.id}
            benchmarkCase={benchmarkCase}
            variants={results[benchmarkCase.id]}
            loading={activeCase === benchmarkCase.id}
            imageWidth={index.image_width}
            imageHeight={index.image_height}
          />
        ))}
      </div>
    </main>
  );
}
