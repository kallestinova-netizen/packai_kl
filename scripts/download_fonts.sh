#!/bin/bash
# Download Google Fonts for PACK AI brand system
# Fonts: Unbounded (heading), Manrope (body/tags)

set -e

FONTS_DIR="$(dirname "$0")/../assets/fonts"
mkdir -p "$FONTS_DIR"

echo "Downloading Unbounded-Bold..."
curl -L -o "$FONTS_DIR/Unbounded-Bold.ttf" \
  "https://github.com/google/fonts/raw/main/ofl/unbounded/Unbounded%5Bwght%5D.ttf" 2>/dev/null \
  || echo "WARNING: Could not download Unbounded-Bold.ttf — please download manually from Google Fonts"

echo "Downloading Manrope-Bold..."
curl -L -o "$FONTS_DIR/Manrope-Bold.ttf" \
  "https://github.com/google/fonts/raw/main/ofl/manrope/Manrope%5Bwght%5D.ttf" 2>/dev/null \
  || echo "WARNING: Could not download Manrope-Bold.ttf — please download manually from Google Fonts"

# Copy for Regular variant (variable font covers all weights)
if [ -f "$FONTS_DIR/Manrope-Bold.ttf" ]; then
  cp "$FONTS_DIR/Manrope-Bold.ttf" "$FONTS_DIR/Manrope-Regular.ttf"
  echo "Created Manrope-Regular.ttf (variable font)"
fi

echo ""
echo "Fonts downloaded to: $FONTS_DIR"
ls -la "$FONTS_DIR"/*.ttf 2>/dev/null || echo "No .ttf files found"
echo ""
echo "Note: These are variable fonts. Unbounded-Bold.ttf covers all weights of Unbounded."
echo "Manrope-Bold.ttf / Manrope-Regular.ttf are the same variable font file."
