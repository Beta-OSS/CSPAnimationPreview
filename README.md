# CSPAnimationPreview

CSPAnimationPreview is a tool I am developing, designed to preview full-length animations in Clip Studio Paint projects, overcoming the 24-frame limit imposed by the Pro version of CSP. It allows artists to quickly view animations without manually stitching frames together in a video editor for faster reviews.

---

## Overview

CSPAnimationPreview reads structured animation folders from `.clip` files and links them together to produce a smooth, full-animation preview. By extracting layers directly from the `.clip` file and handling animation folders intelligently, it saves time and provides a professional, integrated workflow for digital artists.

The backend layer extraction is built on top of [dobrokot/clip_to_psd](https://github.com/dobrokot/clip_to_psd), which handles `.clip` file parsing and converts CSP layers into PNG images. CSPAnimationPreview extends this functionality by automatically linking animation sections, providing an interactive and user-friendly preview experience.

---

## The Goal

- Provide an easy, fast preview of all frames beyond CSP's 24-frame limit.
- Automatically read and link animation folders for seamless playback.
- Create a professional, easy-to-use application interface designed for digital artists.
- Double-click or "Open With" support for faster workflow.
- Enable fast animation previews directly from `.clip` files.
- Allow interactive folder and frame management within the app.
- Read key settings like frame rate to set them in the preview automatically.

---

## Installation & Usage

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/CSPAnimationPreview.git
   cd CSPAnimationPreview
2. Install requirements:
   ```
   pip install -r requirements.txt
   ```

---

## Contributing

Contributions are welcome. Whether it's improving the GUI, adding features, or optimizing performance, feel free to submit pull requests or open issues, as I aim to be consistent with this project.

---

## References
- [dobrokot/clip_to_psd](https://github.com/dobrokot/clip_to_psd) - Core backend logic for extracting CSP layers as PNGs.
