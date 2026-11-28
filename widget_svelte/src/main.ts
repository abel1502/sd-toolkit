import { defineWidget } from "./anywidget.svelte";
import TagReviewWidget from "./TagReviewWidget.svelte";
import ConfidenceReviewWidget from "./ConfidenceReviewWidget.svelte";
import PreviewWidget from "./PreviewWidget.svelte";
import SelectionWidget from "./SelectionWidget.svelte";
import TagEditorWidget from "./TagEditorWidget.svelte";
import MaskWidget from "./MaskWidget.svelte";
import DeriveWidget from "./DeriveWidget.svelte";
import CropWidget from "./CropWidget.svelte";
import "./app.css";

export default defineWidget({
  tag_review: TagReviewWidget,
  confidence_review: ConfidenceReviewWidget,
  preview: PreviewWidget,
  selection: SelectionWidget,
  tag_editor: TagEditorWidget,
  mask: MaskWidget,
  derive: DeriveWidget,
  crop: CropWidget,
});
