# Redacted brand assets and fonts

Original user-supplied SVGs are preserved in `assets/brand/source/`.
The served black and white logos are in `public/brand/`. Their editable
Courier New text was replaced by Cousine vector outlines, so neither logo
requires an installed or proprietary font. Other artwork is unchanged.

The interface serves its fonts locally from `public/fonts/`:

- Inter: SIL Open Font License 1.1. License: `Inter-OFL.txt`.
  Project: https://github.com/rsms/inter
  Existing WOFF2 originally obtained from Tide's website.
- Cousine Regular: SIL Open Font License 1.1. License: `Cousine-OFL.txt`.
  Font and license: https://github.com/google/fonts/tree/main/ofl/cousine
  Used for typewriter styling and the logo's outlined text.

No runtime font service or paid font subscription is required.
Unused Albert Sans was removed. The legacy Tide logo is not used by the UI.
