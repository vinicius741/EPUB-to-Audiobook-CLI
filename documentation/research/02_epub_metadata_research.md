# EPUB Metadata Extraction Research

## Summary of Findings

EPUB metadata is primarily based on the **Dublin Core Metadata Element Set (DCMES)**. These metadata elements are located in the `content.opf` (Open Packaging Format) file, within the `<metadata>` section.

### Standard Metadata Fields

The 15 core Dublin Core elements used in EPUB are:

1.  **`dc:title`**: Title of the book (Required).
2.  **`dc:creator`**: Primary author or creator (Required in practice, can occur multiple times).
3.  **`dc:identifier`**: Unique ID (ISBN, UUID, etc.) (Required).
4.  **`dc:language`**: Language code (e.g., `en`, `fr`) (Required).
5.  **`dc:subject`**: Keywords or phrases.
6.  **`dc:description`**: Abstract, blurb, or table of contents.
7.  **`dc:publisher`**: Entity responsible for making the resource available.
8.  **`dc:contributor`**: Other contributors (editors, illustrators).
9.  **`dc:date`**: Publication or creation date.
10. **`dc:type`**: Genre or nature of content.
11. **`dc:format`**: Media type/dimensions.
12. **`dc:source`**: Resource from which this one is derived.
13. **`dc:relation`**: Related resources.
14. **`dc:coverage`**: Spatial or temporal scope.
15. **`dc:rights`**: Copyright information.

**Note:** In EPUB 3, `dcterms:modified` is also required.

### Cover Image Extraction

Extracting the cover image involves parsing the OPF file's `<manifest>` section.

**Strategy:**

1.  **EPUB 3 (Standard):** Look for an `<item>` in the `<manifest>` with `properties="cover-image"`.
    ```xml
    <item id="cover" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image" />
    ```
2.  **EPUB 2 (Legacy/Fallback):** Look for a `<meta>` element with `name="cover"`. The `content` attribute refers to the `id` of the cover image in the manifest.
    ```xml
    <metadata>
        <meta name="cover" content="cover-image-item-id" />
    </metadata>
    <manifest>
        <item id="cover-image-item-id" href="cover.jpg" media-type="image/jpeg" />
    </manifest>
    ```

### Edge Cases

1.  **Multiple Authors:**
    *   **Best Practice:** Multiple `<dc:creator>` tags.
    *   **Edge Case:** All authors merged into one tag (e.g., "Author A, Author B").
    *   **Strategy:** Collect all `dc:creator` tags. If only one exists, check for delimiters (comma, ampersand) to potentially split, though this risks splitting "Last, First" name formats.
2.  **Missing Title/Author:**
    *   Rare but possible in poorly formed files.
    *   **Strategy:** Use filename as fallback for title, "Unknown" for author.
3.  **Missing Cover:**
    *   Not all EPUBs have a declared cover.
    *   **Strategy:** If standard methods fail, check for an image named `cover.jpg` or `title.jpg` in the root or images folder, or use a default placeholder.
4.  **Non-Standard Metadata:**
    *   Custom `<meta>` tags may contain useful info like "series" or "series_index" (common in Calibre-processed books).

## Recommended Library & Approach

We are already using **`ebooklib`** (selected in Phase 1).

*   **Metadata:** `ebooklib` provides easy access to Dublin Core metadata via `book.get_metadata('DC', 'field_name')`.
*   **Cover:** `ebooklib` doesn't strictly normalize the "cover" retrieval across versions. We may need to manually check `book.get_items_of_type(ebooklib.ITEM_COVER)` or inspect the OPF metadata manually if `ebooklib`'s abstraction falls short for specific edge cases.

### Code Example (Conceptual)

```python
import ebooklib
from ebooklib import epub

def get_metadata(book):
    title = book.get_metadata('DC', 'title')[0][0]
    creators = [c[0] for c in book.get_metadata('DC', 'creator')]
    return title, creators

def get_cover(book):
    # Try getting explicit cover item
    cover_items = book.get_items_of_type(ebooklib.ITEM_COVER)
    if cover_items:
        return cover_items[0]
    
    # Fallback logic might be needed here to parse OPF manually 
    # if ebooklib misses 'properties="cover-image"'
    return None
```
