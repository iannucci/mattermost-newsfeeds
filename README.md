# mattermost_newsfeeds (v3)

**New formatting options for Mattermost posts**

- `style`: `markdown` (default), `fields`, or `upload`
  - **markdown**: uses templates/markdown (what you saw in v2)
  - **fields**: renders a compact key:value list (top fields shown first)
  - **upload**: uploads a JSON file of the payload and posts a short message (useful for long batches)
- `thread_root_id`: if set, will post **replies in a thread** under this root post
- `batch_threshold`: when posting **batches**, if `len(items) >= batch_threshold` and style is `upload`, the file-upload branch is used
- `stream`: true/false — stream each item as it arrives (true) or batch per poll (false)

**File upload** requires bot mode and a resolvable channel id.

Config lookup:
- prefers `./config.json` (current working directory)
- else `/etc/mattermost_newsfeeds/config.json`

Install as before; only `util/notifier.py` is richer now.
