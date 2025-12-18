#!/bin/bash

# ============================
# Batch XSLT transformation
# TEI P5 → static HTML
# Varela Digital
# ============================

# --- Configuration ---
SAXON_JAR="tools/saxon/saxon-he.jar"
XSLT_FILE="xslt/tei_document_to_html.xsl"
INPUT_DIR="data/documents_XML"
OUTPUT_DIR="data/documents_HTML"

# --- Checks ---
if [ ! -f "$SAXON_JAR" ]; then
  echo "ERROR: Saxon-HE JAR not found at $SAXON_JAR"
  echo "Please download Saxon-HE and place it in tools/saxon/"
  exit 1
fi

if [ ! -f "$XSLT_FILE" ]; then
  echo "ERROR: XSLT file not found: $XSLT_FILE"
  exit 1
fi

if [ ! -d "$INPUT_DIR" ]; then
  echo "ERROR: Input directory not found: $INPUT_DIR"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

# --- Transformation ---
echo "Starting batch XSLT transformation..."

for xml_file in "$INPUT_DIR"/*.xml; do
  filename=$(basename "$xml_file" .xml)
  output_file="$OUTPUT_DIR/$filename.html"

  echo "Processing $filename.xml → $filename.html"

  java -jar "$SAXON_JAR" \
       -s:"$xml_file" \
       -xsl:"$XSLT_FILE" \
       -o:"$output_file"
done

echo "Batch transformation completed."