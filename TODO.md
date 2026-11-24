- Migrate existing scripts in my_loras
- Remove the old files from `C:\AI\source_images\grabber`

- Training supervision module (auto-add `.civitai.info` and `.json`, callback for making previews, copy to _my)

- Training process integration
  - Store and write out configs at least.
  - Possibly also invoke training script, watch directory for new epochs and add
    metadata automatically. Perhaps even auto-generate previews (or make an sd-webui script to do that easily)
  - Post-process: add metadata (json and civitai.info), maybe previews, filter tags in lora metadata

- Add character-to-series inference, either to the autotagger or as a Tags method?
- Add danbooru tag database knowledge (currently only pixiv aliases, perhaps also category inference and more)
- Add LLM-powered autotagging for OCR
- Derived images (`DerivedImages`):
  - Add video and ugoira (zip) frame extraction
  - Add a UI for image cropping (`DerivedImages.crop` exists, but needs the box specified manually)
- AI-toolkit config generation?
  - Generalize under one abstraction, perhaps?
  - Support multiple datasets in both cases
  - Can run jobs programmatically
  - Maybe also implement an extension to ai-toolkit?
    - Protected tags, instead of a single trigger
    - Tag dropout
    - Models in non-diffusers format?
  - Also expose configs publicly
- In TaggerConfig, add `\` to the sample prompts automatically. Also some convenience wrapper for making a prompt from only the substantial part.
- Add an API wrapper for sd-webui-forge-neo
  - Here or in idofront. In fact, maybe merge idofront into here?
- Embedding generation with a vision model, then guided clustering (i.e. boolean tag prediction)?
  - Useful for selecting things to tag that are hard to define
  - Would need a UI widget
  - Use Nvidia Kumo for tag prediction?
- CLI
  - Some commands specific to me:
    - `_process_civitai.py`, `_add_metadata.py`
      - Maybe not incorporate the raw scripts at first, but simply expose an alias?
    - "set up a directory for a lora" (templated `./scrape.ps1` + `.vscode` + `anima/[name].ipynb`)
    - May need to be at least partially defined within user config

