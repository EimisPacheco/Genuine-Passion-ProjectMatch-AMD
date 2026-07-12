# Fixed clip set — Gemma 4-style captioning (agent 11)

Drop short video clips here and the pipeline's **Clip Captioning** agent samples
frames from each and asks **Gemma vision on the AMD MI300X** for a caption in
four styles: **formal**, **sarcastic**, **humorous-tech**, **humorous-non-tech**.
They appear in the analysis **🎬 Captions** tab.

## How to add clips

1. Copy a few **short** clips into this folder. Supported: `.mp4 .mov .webm .mkv .m4v`.
   Keep them short (a few seconds) — we sample the start/middle/end frames.
2. (Optional) add a `clips.json` manifest to give each clip a title and a citable
   source URL:

   ```json
   [
     { "file": "demo_ui.mp4", "title": "App demo — dashboard", "source_url": "https://github.com/user/repo" },
     { "file": "architecture.mp4", "title": "Architecture walkthrough", "source_url": "" }
   ]
   ```

   Without a manifest, the title is derived from the filename and the source URL is blank.

## Notes

- Needs `ffmpeg` (frame extraction) + a vision provider (Gemma on AMD, or Gemini
  fallback). With neither, the agent emits a deterministic placeholder caption so
  the pipeline never fails.
- The clip set is **fixed** (this folder) and independent of the candidates.
