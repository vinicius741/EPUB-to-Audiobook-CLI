# EPUB Reader and TOC/Reading Order Extraction Research

## 1. EPUB File Format: 2.0 vs 3.0

EPUB (Electronic Publication) is the industry-standard e-book format. The CLI must handle both major versions robustly.

| Feature | EPUB 2.0 | EPUB 3.0 |
| :--- | :--- | :--- |
| **Core Standard** | XHTML 1.1, CSS 2.1 | HTML5, CSS3 |
| **Multimedia** | Basic images, limited audio/video | Native `<audio>`, `<video>`, SVG, Canvas |
| **Navigation** | NCX (`.ncx` file) - Hierarchical TOC | Navigation Document (`nav` HTML5 `<nav>`) + NCX (for backward compat) |
| **Layout** | Reflowable only | Reflowable + Fixed Layout |
| **Scripting** | None (official) | JavaScript enabled |
| **Metadata** | Dublin Core (limited) | Dublin Core + Meta tags (richer) |

**Implication for Project:**
*   The parser must support both NCX (2.0) and Navigation Document (3.0) for TOC extraction.
*   We generally ignore multimedia/scripting for "Text-to-Audio" conversion, focusing on the text content in the HTML5/XHTML docs.

## 2. Python Library Evaluation

We evaluated libraries based on parsing capability, maintenance, and support for structural extraction (TOC/Spine).

| Library | Type | Pros | Cons | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **`ebooklib`** | Parser/Builder | Supports EPUB 2 & 3. Full access to spine, TOC, metadata. Active maintenance. | Doesn't render HTML to text (needs `BeautifulSoup`). | **Recommended** |
| `epub2txt` | Converter | Easy text extraction. | Opaque. Hard to customize chapter splitting or ignore specific sections. | No |
| `pypub` | Builder | Great for *creating* EPUBs. | Not designed for parsing existing files. | No |
| `tika-python` | Wrapper | Handles everything (PDF, DOCX, etc). | Heavy dependency (Java/Tika). Overkill. | No |

**Selected Library: `ebooklib`**
*   **Reason:** It provides granular access to the EPUB structure (`spine`, `toc`, `metadata`) rather than just dumping text. This is critical for generating separate audio chapters.
*   **Dependency:** Will require `BeautifulSoup4` (bs4) to clean the HTML content extracted by `ebooklib`.

## 3. Implementation Strategy

### A. TOC (Table of Contents) Extraction
The TOC represents the logical hierarchy of the book (Chapters, Sub-chapters). In `ebooklib`, this is available via `book.toc`.

*   **Structure:** `book.toc` is a nested list/tuple structure.
    *   Items can be `epub.Link` (leaf node, points to a file).
    *   Items can be `(epub.Section, [children...])` (node with title and subsections).
*   **Strategy:** We need a recursive function to flatten this or map it to our internal Chapter representation.

**Code Snippet (Concept):**
```python
def extract_toc(book):
    # Recursively traverse book.toc
    for item in book.toc:
        if isinstance(item, epub.Link):
            print(f"Chapter: {item.title} -> {item.href}")
        elif isinstance(item, tuple) and len(item) == 2:
            section, children = item
            print(f"Section: {section.title}")
            extract_toc(children) # Recurse
```

### B. Reading Order (Spine) Extraction
The "Spine" defines the linear reading order of the book. This is what an e-reader follows when you click "Next Page". This is **more important** for an audiobook than the TOC, as we want to read everything in order, even if it's not listed in the TOC (e.g., Dedications, Prefaces).

*   **Access:** `book.spine`
*   **Structure:** A list of `(item_id, linear_flag)`.
    *   `item_id`: ID reference to the file in the manifest.
    *   `linear`: "yes" (default) or "no" (auxiliary content like popup notes).
*   **Strategy:** Iterate through the spine. If `linear="yes"`, resolve the `item_id` to the actual HTML content.

**Code Snippet (Concept):**
```python
def extract_reading_order(book):
    for item_id, linear in book.spine:
        if linear != 'yes':
            continue # Skip non-linear content (optional decision)
        
        item = book.get_item_with_id(item_id)
        if item:
             # This is the HTML content for this section
             html_content = item.get_content()
```

## 4. Recommended Workflow for Phase 1

1.  **Load Book:** `book = epub.read_epub('book.epub')`
2.  **Traverse Spine:** Iterate `book.spine` to get the linear sequence of content documents.
3.  **Map to TOC (Optional but good):** Try to correlate Spine items with TOC entries to get nice Chapter Titles (e.g., "Chapter 1"). If a Spine item isn't in the TOC, fallback to a generic name or use the HTML `<title>` tag.
4.  **Extract Text:** For each Spine item (HTML document):
    *   Pass content to `BeautifulSoup(content, 'html.parser')`.
    *   Strip boilerplate (nav, header, footer).
    *   Extract clean text.
5.  **Result:** An ordered list of `Chapter` objects: `[{title: "Chap 1", text: "..."}, {title: "Chap 2", text: "..."}]`.

## 5. Edge Cases & Risks
*   **Missing TOC:** Some cheap EPUBs have no TOC. Rely on Spine.
*   **Disordered TOC:** TOC might not match Spine order. Always prioritize Spine for the audio stream.
*   **Non-Linear Content:** Decide whether to read `linear="no"` items (usually skipped).
*   **Complex HTML:** `BeautifulSoup` usage will need robust filters to remove page numbers, hidden text, or excessive whitespace.
