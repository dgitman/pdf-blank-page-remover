import os
import unicodedata
import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DRIVE_ROOT = '/content/drive/MyDrive'
REVIEW_FOLDER = os.path.join(DRIVE_ROOT, 'Blank Pages Review')

# Dual-condition blank-page detection thresholds (tuned on real-world scans):
#
#   MIN_READABLE_CHARS – minimum number of proper Unicode letters/digits/
#     punctuation that a page must contain to be considered non-blank by the
#     text check.  Garbage OCR artefacts on visually-blank pages typically
#     produce fewer than 30 characters; real content pages produce hundreds.
#     Set to 50 to give a safe margin.
#
#   BLANK_THRESHOLD – maximum fraction of non-white pixels (grayscale < 250)
#     at 72 DPI for a page to be considered blank by the pixel check.
#     Scanner-noise blanks are typically 0–3 %; real pages are well above 5 %.
#     Set to 0.05 (5 %) so light scanner-noise blanks are caught while real
#     pages with only a little ink are kept.
#
# A page is removed only when BOTH conditions hold simultaneously:
#   readable chars < MIN_READABLE_CHARS  AND  non-white pixel ratio < BLANK_THRESHOLD
MIN_READABLE_CHARS = 50
BLANK_THRESHOLD    = 0.05  # 5 % non-white pixels


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fix_structure_tree(doc):
        """Remove a broken tagged-PDF structure tree from the document catalog.

            The 'No common ancestor in structure tree' MuPDF error occurs when a PDF
                declares itself as a tagged PDF (MarkInfo + StructTreeRoot in the catalog)
                    but the structure tree is malformed. The page content and visual appearance
                        are completely unaffected by the structure tree, so we safely delete those
                            two catalog entries to prevent MuPDF from traversing the broken tree.

                                This is a true fix: after calling this, MuPDF never encounters the bad
                                    structure tree and the error does not occur at all.
                                        """
        try:
                    catalog_xref = doc.pdf_catalog()
                    if catalog_xref <= 0:
                                    return  # not a writable PDF
        struct_root = doc.xref_get_key(catalog_xref, "StructTreeRoot")
            if struct_root[0] in ("null", "none"):
                            return  # no structure tree present, nothing to fix
        # Delete the broken structure tree from the catalog
        doc.xref_set_key(catalog_xref, "StructTreeRoot", "null")
        doc.xref_set_key(catalog_xref, "MarkInfo", "null")
except Exception:
        pass  # safe to ignore if not writable


def has_meaningful_text(page):
        """Return True if the page contains enough real readable characters.

            Counts Unicode letters, digits, and punctuation (by Unicode category).
                Garbage OCR artefacts on visually-blank scanned pages produce only a
                    handful of stray characters; real content pages produce hundreds.
                        """
    raw = page.get_text("text")
    readable_cats = (
                'Lu', 'Ll', 'Lt', 'Lm', 'Lo',   # letters
        'Nd', 'Nl', 'No',                 # numbers
        'Po', 'Ps', 'Pe', 'Pi', 'Pf',    # punctuation
        'Sm', 'Sc',                        # math / currency symbols
    )
    readable = sum(1 for ch in raw if unicodedata.category(ch) in readable_cats)
    return readable >= MIN_READABLE_CHARS


def is_blank_page(page, dpi=72):
        """Return True only when BOTH conditions hold:
              1. Fewer than MIN_READABLE_CHARS proper letters/digits/punctuation chars.
                    2. Fewer than BLANK_THRESHOLD fraction of pixels are non-white.

                        Using both conditions prevents false positives on lightly-inked real pages
                            (caught by text check) and false negatives on blank pages with OCR garbage
                                (caught by pixel check).
                                    """
    try:
                # --- Text check ---
                if has_meaningful_text(page):
                                return False  # real text content → keep

        # --- Pixel check ---
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
                data = pix.samples
                total = len(data)
                if total == 0:
                                return False
                            non_white = sum(1 for b in data if b < 250)
        return (non_white / total) < BLANK_THRESHOLD

except Exception:
        return False  # on any error, keep the page


def find_all_pdfs(root, skip_dir=None):
        """Yield paths to every PDF under *root*, skipping *skip_dir* entirely."""
    if skip_dir is not None:
                skip_prefix = os.path.normpath(skip_dir) + os.sep
    for dirpath, dirs, filenames in os.walk(root):
                if skip_dir is not None:
                                norm_dirpath = os.path.normpath(dirpath) + os.sep
                                if (norm_dirpath.startswith(skip_prefix) or
                                                        os.path.normpath(dirpath) == os.path.normpath(skip_dir)):
                                                                            dirs.clear()
                                                                            continue
                                                                    for fn in filenames:
                                                                                    if fn.lower().endswith('.pdf'):
                                                                                                        yield os.path.join(dirpath, fn)


def page_nums_str(indices):
        """Return a human-readable list of 1-based page numbers, e.g. 'p2_p4'."""
    return '_'.join(f'p{i + 1}' for i in sorted(indices))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

os.makedirs(REVIEW_FOLDER, exist_ok=True)

all_pdfs    = list(find_all_pdfs(DRIVE_ROOT, skip_dir=REVIEW_FOLDER))
total_pdfs  = len(all_pdfs)
total_removed = 0
errors = 0

print(f"Found {total_pdfs} PDFs to process.")
print(f"Review folder: {REVIEW_FOLDER}")
print("-" * 60)

for idx, pdf_path in enumerate(all_pdfs, 1):
        rel = os.path.relpath(pdf_path, DRIVE_ROOT)
    print(f"[{idx}/{total_pdfs}] {rel}", end="")
    try:
                doc = fitz.open(pdf_path)
        if doc.is_encrypted:
                        print(" [encrypted, skipped]")
            doc.close()
            continue

        fix_structure_tree(doc)

        n = doc.page_count
        print(f" | Pages: {n}", end="")

        blank_indices = [i for i in range(n) if is_blank_page(doc[i])]

        if not blank_indices:
                        print()
            doc.close()
            continue

        print(f" | Blank pages: {[i+1 for i in blank_indices]}")

        # Save extracted blank pages to the review folder
        base        = os.path.splitext(os.path.basename(pdf_path))[0]
        review_name = f"{base}_blank_{page_nums_str(blank_indices)}.pdf"
        review_path = os.path.join(REVIEW_FOLDER, review_name)
        review_doc  = fitz.open()
        for i in blank_indices:
                        review_doc.insert_pdf(doc, from_page=i, to_page=i)
        review_doc.save(review_path)
        review_doc.close()
        print(f"  Blank pages saved -> Blank Pages Review/{review_name}")

        # Remove blank pages from original (reverse order to keep indices valid)
        for i in sorted(blank_indices, reverse=True):
                        doc.delete_page(i)
        doc.save(pdf_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc.close()
        print(f"  Cleaned PDF saved -> {rel}")
        total_removed += len(blank_indices)

except Exception as e:
        print(f" [ERROR: {e}]")
        errors += 1

print()
print(f"Done! Removed {total_removed} blank page(s) across all PDFs.")
print(f"Errors skipped: {errors}")
print(f"Review folder: {REVIEW_FOLDER}")
