# Wallet icon provenance (reproducible chain)

- Source asset: `branding/icon-source.jpg` — the MAZA coin roundel supplied
  by Sami (2026-11-16, Telegram), the official mazacoin.org artwork
  (black/red/yellow quadrants, orange M glyph).
- Source SHA-256: `963213d97ca7d2b18313f4fc092fecb60cc3db499b9eea8979fd55b0f9cc0225`
  (1024x1024 JPG, RGB, black background).
- Transformation to `walletbench/static/icon.png` (512px):
  PIL: `Image.open(src).convert("RGBA")` then `.resize((512, 512),
  Image.LANCZOS)`, saved as PNG.
- Transformation to `android/res/mipmap-*/ic_launcher.png`:
  same source, resized to 48/72/144/192/240px per density, same pipeline.
- Replaced the MiniMax-generated placeholder at Sami's direction
  ("make this the coin mobile wallet logo", 2026-11-16).

Verify: hash `branding/icon-source.jpg` against the pin above, apply the
transform, and compare against the vendored assets.
