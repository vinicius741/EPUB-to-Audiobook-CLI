
import ebooklib
from ebooklib import epub
import os

def run_experiment():
    filename = 'test_metadata.epub'
    
    # 1. Create a book with rich metadata
    book = epub.EpubBook()
    book.set_identifier('TEST-ID-123')
    book.set_title('Test Book Title')
    book.set_language('en')
    book.add_author('Author One')
    book.add_author('Author Two')
    book.add_metadata('DC', 'description', 'This is a test description.')
    book.add_metadata('DC', 'publisher', 'Test Publisher')
    
    # Add a cover
    cover_content = b'fake_image_content'
    book.set_cover('cover.jpg', cover_content)
    
    # Write it
    epub.write_epub(filename, book)
    
    # 2. Read it back
    read_book = epub.read_epub(filename)
    
    # 3. Inspect Metadata Structure
    print("--- Metadata Inspection ---")
    
    keys = ['title', 'creator', 'language', 'identifier', 'description', 'publisher']
    for key in keys:
        data = read_book.get_metadata('DC', key)
        print(f"Key: {key}")
        print(f"Raw: {data}")
        # Verify access pattern
        if data:
            # Usually we want the text content
            # Let's see what the first item looks like
            first_item = data[0]
            print(f"First Item Type: {type(first_item)}")
            print(f"First Item Value: {first_item}")
        print("-" * 20)

    # 4. Inspect Cover
    print("--- Cover Inspection ---")
    cover = read_book.get_cover() # This returns an EpubItem according to docs?
    if cover:
        print(f"Cover Type: {type(cover)}")
        print(f"Cover ID: {cover.get_id()}")
        print(f"Cover Name: {cover.get_name()}")
        print(f"Cover Media Type: {cover.media_type}")
    else:
        print("No cover found via get_cover()")

    # Cleanup
    if os.path.exists(filename):
        os.remove(filename)

if __name__ == '__main__':
    run_experiment()
