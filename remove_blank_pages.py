import os
import fitz

# Configuration
DRIVE_ROOT = '/content/drive/MyDrive'
REVIEW_FOLDER = os.path.join(DRIVE_ROOT, 'Blank Pages Review')
BLANK_THRESHOLD = 0.005  # 0.5% non-white pixels = blank


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


def is_blank_page(page, dpi=72):
    """Return True if the page renders as nearly all white."""
    try:
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        data = pix.samples
        total = len(data)
        if total == 0:
            return False
        non_white = sum(1 for b in data if b < 250)
        return (non_white / total) < BLANK_THRESHOLD
    except Exception:
        return False


def find_all_pdfs(root):
    """Walk root and yield every .pdf path."""
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith('.pdf'):
                yield os.path.join(dirpath, fn)


def page_nums_str(indices):
    """Convert 0-based page indices to 1-based page number string like p2_p5."""
    return '_'.join(f'p{i+1}' for i in sorted(indices))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
os.makedirs(REVIEW_FOLDER, exist_ok=True)

# Collect all PDFs (skip files already in the review folder)
all_pdfs = sorted([
    p for p in find_all_pdfs(DRIVE_ROOT)
    if not os.path.abspath(p).startswith(os.path.abspath(REVIEW_FOLDER))
])
total_pdfs = len(all_pdfs)
total_removed = 0
errors = 0

print(f"Found {total_pdfs} PDFs to process.")
print(f"Review folder: {REVIEW_FOLDER}")
print("-" * 60)

for idx, pdf_path in enumerate(all_pdfs, start=1):
    rel_path = os.path.relpath(pdf_path, DRIVE_ROOT)
    print(f"[{idx}/{total_pdfs}] {rel_path}", flush=True)

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  ERROR opening: {e}", flush=True)
        errors += 1
        continue

    if doc.is_encrypted:
        print(f"  SKIPPED (encrypted)", flush=True)
        doc.close()
        continue

    # Fix broken tagged-PDF structure tree BEFORE rendering any pages.
    # This prevents MuPDF from raising "No common ancestor in structure tree"
    # during get_pixmap(), because the bad StructTreeRoot is removed from the
    # catalog and MuPDF never tries to traverse it.
    fix_structure_tree(doc)

    n_pages = len(doc)

    try:
        blank_indices = [i for i in range(n_pages) if is_blank_page(doc[i])]
    except Exception as e:
        print(f"  ERROR reading pages: {e}", flush=True)
        try:
            doc.close()
        except Exception:
            pass
        errors += 1
        continue

    if not blank_indices:
        doc.close()
        continue

    print(f"  Pages: {n_pages} | Blank pages: {blank_indices}", flush=True)

    # Build review filename with page numbers
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    pg_str = page_nums_str(blank_indices)
    review_name = f"{base_name}_blank_{pg_str}.pdf"
    review_path = os.path.join(REVIEW_FOLDER, review_name)
    counter = 1
    while os.path.exists(review_path):
        review_name = f"{base_name}_blank_{pg_str}_{counter}.pdf"
        review_path = os.path.join(REVIEW_FOLDER, review_name)
        counter += 1

    # Save blank pages to review folder
    try:
        blank_doc = fitz.open()
        for i in blank_indices:
            blank_doc.insert_pdf(doc, from_page=i, to_page=i)
        blank_doc.save(review_path, garbage=4, deflate=True)
        blank_doc.close()
        print(f"  Blank pages saved -> Blank Pages Review/{review_name}", flush=True)
    except Exception as e:
        print(f"  ERROR saving blank pages: {e}", flush=True)
        errors += 1

    # Build and save cleaned PDF (non-blank pages only)
    try:
        clean_doc = fitz.open()
        for i in range(n_pages):
            if i not in blank_indices:
                clean_doc.insert_pdf(doc, from_page=i, to_page=i)
        doc.close()
        clean_doc.save(pdf_path, garbage=4, deflate=True)
        clean_doc.close()
        print(f"  Cleaned PDF saved  -> {rel_path}", flush=True)
        total_removed += len(blank_indices)
    except Exception as e:
        print(f"  ERROR saving cleaned PDF: {rel_path}  ({e})", flush=True)
        try:
            doc.close()
        except Exception:
            pass
        errors += 1
        continue

print()
print(f"Done! Removed {total_removed} blank page(s) across all PDFs.")
print(f"Errors skipped: {errors}")
print(f"Review folder: {REVIEW_FOLDER}")

