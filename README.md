# pdf-blank-page-remover

A Python script that scans all PDFs in your Google Drive, removes blank pages in-place, and saves the removed blank pages to a dedicated review folder so you can verify the results.

Designed to run in **Google Colab** with Google Drive mounted — no local setup required.

---

## Features

- Scans every PDF in your Google Drive recursively
- Detects blank pages by rendering each page as a grayscale image and checking that fewer than 0.5% of pixels are non-white
- Removes blank pages from the original PDF (overwrites in-place)
- Saves the removed blank pages to a `Blank Pages Review/` folder, named with the original filename and the page numbers extracted (e.g. `Invoice_blank_p2_p5.pdf`)
- Shows real-time progress: `[142/5166] Family/Taxes/2021/Tax Return.pdf`
- Skips encrypted PDFs gracefully
- **Fixes** (not just suppresses) the MuPDF `"No common ancestor in structure tree"` error by removing the malformed tagged-PDF structure tree from the document catalog before rendering

---

## Requirements

- Google Colab (free tier works)
- Google Drive with PDFs
- PyMuPDF (`pymupdf`) — installed automatically in the setup cell

---

## How to Use

### Step 1 — Open Google Colab

Go to [colab.research.google.com](https://colab.research.google.com) and create a new notebook.

### Step 2 — Install dependencies and mount Google Drive

Paste this into the first cell and run it:

```python
!pip install pymupdf -q
from google.colab import drive
drive.mount('/content/drive')
```

When prompted, allow access to your Google Drive. You should see:

```
Mounted at /content/drive
```

### Step 3 — Run the script

Paste the contents of `remove_blank_pages.py` into a new cell and run it.

The script will:
1. Walk your entire Google Drive and collect all PDF paths
2. Print a progress line for every file: `[X/total] path/to/file.pdf`
3. For each PDF that contains blank pages:
   - Print the blank page numbers found
   - Save a copy of the blank pages to `My Drive/Blank Pages Review/`
   - Overwrite the original PDF with the blank pages removed
4. Print a final summary when done

**Example output:**

```
Found 5166 PDFs to process.
Review folder: /content/drive/MyDrive/Blank Pages Review
------------------------------------------------------------
[1/5166] Family/Cars/2005 Honda Accord/Purchase/Invoice.pdf
[2/5166] Family/Cars/2005 Honda Accord/Insurance/Policy.pdf
  Pages: 12 | Blank pages: [1, 9]
  Blank pages saved -> Blank Pages Review/Policy_blank_p2_p10.pdf
  Cleaned PDF saved  -> Family/Cars/2005 Honda Accord/Insurance/Policy.pdf
...
Done! Removed 47 blank page(s) across all PDFs.
Errors skipped: 2
Review folder: /content/drive/MyDrive/Blank Pages Review
```

### Step 4 — Review the extracted blank pages

Open your Google Drive and navigate to the **`Blank Pages Review`** folder. Each file there is named after its source document and includes the original page numbers in the filename (1-based), so you can cross-reference easily.

---

## Configuration

At the top of `remove_blank_pages.py` you can adjust:

| Variable | Default | Description |
|---|---|---|
| `DRIVE_ROOT` | `/content/drive/MyDrive` | Root folder to scan |
| `REVIEW_FOLDER` | `DRIVE_ROOT/Blank Pages Review` | Where extracted blank pages are saved |
| `BLANK_THRESHOLD` | `0.005` | Fraction of non-white pixels below which a page is considered blank (0.5%) |

---

## How Blank Detection Works

Each page is rendered at 72 DPI as a grayscale image. A pixel is considered "non-white" if its value is below 250 (out of 255). If fewer than `BLANK_THRESHOLD` (0.5%) of pixels are non-white, the page is classified as blank.

This catches:
- Completely empty pages
- Pages with only faint artifacts or compression noise
- Near-white pages with a very light background

---

## The MuPDF Structure Tree Fix

Some PDFs declare themselves as tagged/accessible documents (they have `MarkInfo` and `StructTreeRoot` entries in the PDF catalog) but contain a malformed structure tree. When PyMuPDF tries to render a page, MuPDF walks this tree and raises:

```
MuPDF error: format error: No common ancestor in structure tree
```

This script **fixes** the problem rather than suppressing it. Before rendering any pages, `fix_structure_tree(doc)` checks whether the document has a `StructTreeRoot` catalog entry and, if so, removes it (along with `MarkInfo`) in memory. Since the structure tree is only used for accessibility tagging and has no effect on visual page content, removing it is completely safe and does not alter the rendered output.

```python
def fix_structure_tree(doc):
    catalog_xref = doc.pdf_catalog()
    struct_root = doc.xref_get_key(catalog_xref, "StructTreeRoot")
    if struct_root[0] not in ("null", "none"):
        doc.xref_set_key(catalog_xref, "StructTreeRoot", "null")
        doc.xref_set_key(catalog_xref, "MarkInfo", "null")
```

---

## License

MIT
