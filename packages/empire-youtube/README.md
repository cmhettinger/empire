# empire-youtube

`empire-youtube` provides reusable YouTube metadata scraping utilities for
Empire.

The package is metadata-only:

- API key authentication through `EMPIRE_YOUTUBE_GOOGLE_API_KEY`
- no OAuth
- no browser automation
- no video downloads
- no thumbnail downloads

Runtime callers provide scraper configuration from a file path, YAML string,
mapping, or future object-store backed loader. The package does not load `.env`
files and does not assume where operational config lives in the monorepo.

## Language Filtering

`youtube.filters.language` is sent to YouTube search as `relevanceLanguage`.
After video hydration, videos that declare a different default language or
default audio language are excluded. Videos with no declared language are kept,
because many valid English videos do not populate those metadata fields.

## API Usage

Topic discovery uses `search.list` and is throttled by default to one search
request every seven seconds. Followed channels use each channel's public uploads
playlist instead of `search.list`, then apply the configured lookback window
after video hydration.

## Channel Resolver

Use the repo-level helper to resolve a YouTube handle, channel id, or search
query into a config-ready channel block:

```bash
bin/youtube-resolve-channel @grahamhancock
bin/youtube-resolve-channel @allin
bin/youtube-resolve-channel @TheRandallCarlson
```

Example output:

```yaml
channel_name: Graham Hancock Official Channel
channel_id: UCk_foUwmaHeFhmAZMnEHQsw
handle: '@grahamhancock'
enabled: true
```

Paste the output under `youtube.followed_channels` in:

```text
object-store/config/youtube/config.yml
```

## Output Contract

The scraper returns one consolidated JSON payload for downstream reports and
storage:

```json
{
  "source": "youtube",
  "schema_version": 1,
  "generated_at": "2026-05-23T22:00:00Z",
  "window_hours": 26,
  "run_id": "d7e5c5f9-6a5c-4f18-9b1d-8fd1c0d2f92f",
  "config": {
    "name": "daily_youtube_scraper",
    "version": 1
  },
  "videos": []
}
```

Each video includes normalized metadata, thumbnails, statistics, YouTube-specific
fields, and discovery provenance such as matched sections, topics, queries,
channels, and discovery sources.

## Object Store Output

Empire-backed runs write normalized JSON to the object store by default:

```text
youtube/YYYY/MM/DD/{run_id}/youtube-scraper.json
```

The object metadata uses:

```text
domain = youtube
object_kind = normalized_payload
content_type = application/json
```

For local debugging, callers can also write a result to an explicit filesystem
path:

```python
from empire_youtube import write_result_to_file

write_result_to_file(result, "build/youtube/youtube-scraper.json")
```

## Scraper Runner

Run the daily scraper from the repo-level helper:

```bash
bin/youtube-scrape
```

By default, config is loaded from the Empire object store using logical name
`youtube-daily-config`, and output is written back to the object store.

Publish the local config into object store with:

```bash
bin/youtube-put-config
```

For local bootstrap or development, pass a config file explicitly:

```bash
bin/youtube-scrape --config-file object-store/config/youtube/config.yml
```

To bypass object-store output for local debugging, provide an output file:

```bash
bin/youtube-scrape \
  --config-file object-store/config/youtube/config.yml \
  --output-file /tmp/youtube-scraper.json
```

## Processor Runner

Stage 2 reads scraper JSON from a local file, a stored object id, or a prior run
id. The run-level library plan is written to the `global` storage root under
`EMPIRE_STORAGE_KEY_YOUTUBE`; media sidecars are written to the `jellyfin`
storage root so the Jellyfin container can consume them.

```bash
bin/youtube-process --input-file /tmp/youtube-scraper.json
bin/youtube-process --input-object-id 00000000-0000-0000-0000-000000000000
bin/youtube-process --input-run-id 00000000-0000-0000-0000-000000000000
```

For each scraped video, stage 2 writes Jellyfin movie sidecars under:

```text
media/youtube/{channel}/{published-date} - {title} [{video_id}]/
```

Each video folder contains:

```text
empire.json
movie.nfo
fanart.jpg   # when a thumbnail URL is available
```

The future downloader stage should write the video itself as:

```text
movie.mp4
```

Stage 2 also writes a v1 run-level library plan to the `global` run folder:

```text
youtube/YYYY/MM/DD/{run_id}/youtube-library-plan.json
```

The object metadata uses:

```text
domain = youtube
object_kind = jellyfin_library_plan
content_type = application/json
```

The processor produces Jellyfin-compatible sidecar content, while `ObjectStore`
remains the generic read/write and metadata tool.

Processor sidecars are idempotent by Jellyfin media path. If `empire.json`,
`movie.nfo`, or `fanart.jpg` already exists for a video, the processor skips
that sidecar and records the skip count in the run summary.

## Downloader Runner

Stage 3 downloads one planned video at a time. It reads a processor plan from
either a stored object id or a processor run id, then selects one entry by
YouTube video id.

List available videos in a plan:

```bash
bin/youtube-download \
  --plan-object-id 00000000-0000-0000-0000-000000000000 \
  --list
```

Download one video:

```bash
bin/youtube-download \
  --plan-run-id 00000000-0000-0000-0000-000000000000 \
  --video-id 4oq91rzQcO8
```

The downloader shells out to `yt-dlp`, stages the file under:

```text
${EMPIRE_TEMP_DIR}/youtube/downloads/{run_id}/{video_id}/
```

and stores the final media asset through `ObjectStore.put_file()`:

```text
media/youtube/{channel}/{published-date} - {title} [{video_id}]/movie.mp4
```

Existing `movie.mp4` objects are skipped by path. Download reports are written
under the download run folder:

```text
youtube/YYYY/MM/DD/{download_run_id}/youtube-download-report.json
```

`EMPIRE_YOUTUBE_DAYS_TO_KEEP` controls retention for short-lived YouTube
artifacts and defaults to `10` days when unset. `youtube-scraper.json`,
`movie.mp4`, `empire.json`, `movie.nfo`, `fanart.jpg`, library plans, and
download reports are stored with `expires_at` set that many days after creation
so Empire object-store cleanup can delete them later.

Per-video failures are recorded in the run summary and report object. Airflow
tasks should map over video ids so each video can retry independently.

Cleanup is explicit. To remove the planned video folder sidecars when a
download fails, pass:

```bash
bin/youtube-download \
  --plan-object-id 00000000-0000-0000-0000-000000000000 \
  --video-id 4oq91rzQcO8 \
  --cleanup-on-failure
```

During early testing, omit `--cleanup-on-failure` so failed downloads leave
their `empire.json`, `movie.nfo`, and `fanart.jpg` files available for
inspection and retry.

## Airflow DAGs

The consolidated YouTube/Jellyfin Airflow DAG is manual-only while the pipeline
is being hardened:

```text
dags/youtube/youtube_daily_scrape.py
```

`youtube_daily_scrape` runs the complete pipeline in one Airflow DAG:
`scrape_youtube_metadata` -> `process_youtube_library_plan` ->
`list_download_video_ids` -> mapped `download_one_video` -> `generate_daily_summary`
-> `finalize_downloads`. The complete workflow uses one Empire run context:
the scrape payload, library plan, mapped-download reports, and PDF summary are
stored under the scrape run id. Per-video download reports are kept in that
run's `reports/<video-id>/` folder. Mapped downloads use the `youtube_download`
pool. The final task permits individual download failures
while at least 60% of planned videos download or are already present; adjust
`MINIMUM_DOWNLOAD_SUCCESS_RATE` in the DAG to change that threshold.

Before the threshold is applied, `generate_daily_summary` creates an Empire-
branded PDF cover sheet and run-status report. It records scraped/planned
counts, completed and failed downloads, the success-rate gate, and per-video
exceptions. The PDF is stored in the global YouTube object-store area under
the workflow run's `reports/` folder.

The local Compose stack includes an internal-only `youtube-pot-provider`
service for YouTube Proof of Origin tokens. Airflow passes
`EMPIRE_YOUTUBE_POT_PROVIDER_URL` to yt-dlp; the default local value is
`http://youtube-pot-provider:4416`. Set it to an empty value to disable the
provider for a deployment.

To download only selected videos in a manual DAG run, provide:

```json
{
  "video_ids": ["4oq91rzQcO8", "3aA4NBWiNrA"]
}
```

Mapped downloads remove their planned Jellyfin folder by default when the media
download fails, so the library contains complete videos only. During debugging,
retain a failed video's sidecars by providing:

```json
{
  "cleanup_on_failure": false
}
```

The downloader DAG dynamically maps one Airflow task per video id. Each mapped
task uses the `youtube_download` pool so downloads can be serialized by setting
that pool to one slot. Set `EMPIRE_YOUTUBE_DOWNLOAD_TASK_DELAY_SECONDS` to add
an extra delay before each task invokes `yt-dlp`.
