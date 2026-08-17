# OpenRouter photo detector

## Scope

The optional `openrouter` detection mode finds inner photographic image areas
with a remote vision model. It is available in Quick mode, persistent Projects,
and through the synchronous/background detection APIs. The batch CLI remains
local-only.

Projects persist `openrouter` as their `detection_mode`. Upload-time detection,
Detect Pending, Re-detect All, and single-scan re-detection all use the same
detector, model, area limits, retry policy, and response cache as Quick mode.
The project UI must show the remote-upload disclosure whenever this saved mode
is active. Missing configuration is preserved on the background job as HTTP
503 error metadata; provider/response failures use HTTP 502, and the scan moves
to `failed` so it can be retried.

The server, never the browser, reads `OPENROUTER_API_KEY`. The complete scan is
converted to RGB, resized to at most 2048 pixels on its longest side, encoded as
a quality-90 JPEG, and uploaded as a data URL to OpenRouter and the selected
model provider. The UI must disclose this before use.

`OPENROUTER_MODEL` selects the model and defaults to
`google/gemini-3.7-flash`. Responses use a strict JSON schema containing four
normalized corners (0–1000) for each photograph. Invalid, degenerate, out-of-
area-range, and near-duplicate regions are discarded before API boxes are
created.

## Reliability

Requests time out after 120 seconds. Network failures plus HTTP 408, 409, 429,
and 5xx responses are retried twice with bounded exponential backoff;
`Retry-After` is honored up to ten seconds. Permanent 4xx responses and invalid
JSON/structured output fail immediately. A missing server-side API key returns
HTTP 503; provider and response failures return HTTP 502.

## Local response cache

Successful structured responses are cached by default. The key hashes the
exact prepared JPEG together with the model, endpoint, prompt, schema, and
cache-format version. Changing any of those inputs causes a cache miss. Area
thresholds are intentionally excluded because they are applied locally to the
cached coordinates.

Cache files contain only the provider's JSON response—never the scan bytes or
API key—and are written atomically under `~/.scansplitter/llm-cache/`.
`SCANSPLITTER_DATA_DIR` relocates the normal data root;
`SCANSPLITTER_LLM_CACHE_DIR` overrides only this cache. Set
`SCANSPLITTER_LLM_CACHE=0` to disable reads and writes when a fresh model result
is required. Corrupt/unreadable cache entries and cache write failures are
treated as misses and must not prevent detection.

## Interactive feature parity

Detection modes and settings are an interactive product contract, not separate
Quick and Project features. A change to a mode, setting, upload-time detection,
or re-detection behavior must update both workflows in the same release and add
backend plus frontend regression coverage for both. A deliberate exception is
allowed only when this or another binding specification states the reason and
the user-facing documentation identifies the limitation.
