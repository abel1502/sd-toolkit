- Migrate existing scripts in my_loras
- Remove the old files from `C:\AI\source_images\grabber`

- Training supervision module (auto-add `.civitai.info` and `.json`, callback for making previews, copy to _my)
- Incorporate `_process_civitai.py`, `_add_metadata.py`, , etc.?
- Cannibalize traintrain a bit
- ...

- Training process integration
  - Store and write out configs at least.
  - Possibly also invoke training script, watch directory for new epochs and add
    metadata automatically. Perhaps even auto-generate previews (or make an sd-webui script to do that easily)
  - Post-process: add metadata (json and civitai.info), maybe previews, filter tags in lora metadata
- Add image view widget (maybe use it as default preview for images and datasets)
- Add image selection widget (store yes/no choice for all images, configurable default, 
      plus allow creating new ones -- for now simply by making a copy and opening it in krita for editing)
- Fix preview generation on anima in easy training scripts.

- WDv3Autotagger might give tags with `&#039;`?
- Add character-to-series inference, either to the autotagger or as a Tags method?
- Add danbooru tag database knowledge (currently only pixiv aliases, perhaps also category inference and more)
- Add LLM-powered autotagging for OCR
- Add infrastructure for creating new images (mutable appendix to an otherwise immutable dataset for derived images)
  - Add video and ugoira (zip) frame extraction
  - Add image cropping (creates new image, never modifies existing one! except maybe adjusting a crop before finalizing it)
  - Add a widget for drawing masks
- Add a widget for editing tags fully
  - Might need a textual format for tags that includes metadata? Probably impossible though, since it's arbitrary python objects
  - So instead show all tags as ui elements.
  - Removal is easy. Adding a new one might require adding the tag definition python-side.
  - Can have a shortcut (not as in keybind) for the simple case (programmable default added metadata)
  - Also programmable buttons for quick actions
  - Less reproducible than the first taggerwidget (toggleable tags/groups) -- that one can save the changes and reapply them fully; this one might need to save initial and final state and reapply only if the initial state matches...
- AI-toolkit config generation?
  - Generalize under one abstraction, perhaps?
  - Support multiple datasets in both cases
  - Can run jobs programmatically
  - Maybe also implement an extension to ai-toolkit?
    - Protected tags, instead of a single trigger
    - Tag dropout

