- [ ] Migrate existing scripts in my_loras
- [ ] Remove the old files from `C:\AI\source_images\grabber`

- [ ] Training supervision module (auto-add `.civitai.info` and `.json`, callback for making previews, copy to _my)
- [ ] Incorporate `_process_civitai.py`, `_add_metadata.py`, , etc.?
- [ ] Integrate AI-tagging
- [ ] Cannibalize traintrain a bit
- [ ] ...


Immediate priority TODO:
- [ ] Training process integration
  - Store and write out configs at least.
  - Possibly also invoke training script, watch directory for new epochs and add
    metadata automatically. Perhaps even auto-generate previews (or make an sd-webui script to do that easily)
- [ ] Add image view widget (maybe use it as default preview for images and datasets)
- [ ] Add image selection widget (store yes/no choice for all images, configurable default, 
      plus allow creating new ones -- for now simply by making a copy and opening it in krita for editing)
- [ ] Fix preview generation on anima in easy training scripts.

