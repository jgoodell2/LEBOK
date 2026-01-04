import sys
import re
from pathlib import Path
from bs4 import BeautifulSoup
from weasyprint import HTML, CSS
from fetch_pages import fetch_ordered_pages
from tqdm import tqdm

# Path setup
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

from common.wiki_client import run_graphql_query

OUTPUT_FILENAME = "LEBOK_Guide.pdf"

# CSS for the PDF
PRIMARY_COLOR = "#00629B"
SECONDARY_COLOR = "#000000"  # Black for sub-headers
ACCENT_COLOR = "#00B5E2"
TEXT_COLOR = "#333333"
H1_COLOR = "#0095DF"
H2_COLOR = "#FF6766"
H3_COLOR = "#5EB75F"
H4_COLOR = "#B0B0B0"

# Fonts: Arial (Sans) for Headers, Georgia/Times (Serif) for Body
HEADER_FONT = '"Arial", "Helvetica", sans-serif'
BODY_FONT = '"Georgia", "Times New Roman", serif'

PDF_CSS = CSS(
    string=f"""
    @page {{
        size: Letter;
        margin: 1in;
        @bottom-right {{
            content: counter(page);
            font-family: {HEADER_FONT};
            font-size: 9pt;
            color: #666;
        }}
    }}
    
    body {{
        font-family: {BODY_FONT};
        font-size: 11pt;
        line-height: 1.5;
        color: {TEXT_COLOR};
        text-align: justify;
    }}

    /* Headers */
    h1 {{ 
        font-family: {HEADER_FONT};
        font-weight: bold;
        color: {H1_COLOR};
        font-size: 24pt; 
        /* border-bottom: 2px solid {PRIMARY_COLOR}; */
        padding-bottom: 0.2em;
        margin-top: 0;
        break-before: always;
        text-align: left;
    }}
    
    h2 {{ 
        font-family: {HEADER_FONT};
        font-weight: bold;
        color: {H2_COLOR};
        font-size: 18pt; 
        /* border-bottom: 1px solid #ccc; */
        padding-bottom: 0.1em;
        margin-top: 2em;
        margin-bottom: 0.5em;
    }}
    
    h3 {{ 
        font-family: {HEADER_FONT};
        font-weight: bold;
        color: {H3_COLOR};
        font-size: 14pt; 
        margin-top: 1.5em;
        margin-bottom: 0.5em;
    }}
    
    h4, h5, h6 {{
        font-family: {HEADER_FONT};
        font-weight: bold;
        color: {H4_COLOR};
        text-decoration: underline;
        font-size: 12pt;
        margin-top: 1.2em;
    }}

    /* Links */
    a {{ color: {PRIMARY_COLOR}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* Lists */
    ul, ol {{ margin-top: 0.5em; margin-bottom: 0.5em; }}
    li {{ margin-bottom: 0.3em; }}

    /* Images */
    img {{ max-width: 100%; height: auto; }}

    /* Footnotes Area */
    .chapter-footnotes {{
        margin-top: 3em;
        padding-top: 1em;
        border-top: 1px solid #000;
        font-size: 9pt;
        font-family: {HEADER_FONT};
        page-break-inside: avoid;
    }}
    .chapter-footnotes h3 {{
        margin-top: 0;
        font-size: 10pt;
        text-transform: uppercase;
        color: {TEXT_COLOR};
        border: none;
    }}
    .footnotes-list {{ padding-left: 1.5em; }}
    
    /* Table of Contents Styling */
    #home ul {{ 
        list-style-type: none; 
        padding-left: 0; 
    }}
    
    #home li {{ 
        margin-bottom: 0.2em; 
    }}
    
    #home a {{ 
        font-weight: bold; 
        color: {TEXT_COLOR};
        text-decoration: none;
        display: block; /* Ensures the row takes up full width */
    }}
    
    /* The Magic: Adds dots and page number */
    #home a::after {{
        content: leader('.') target-counter(attr(href), page);
        font-weight: normal;
    }}"""
)


def get_page_content(path):
    """
    Fetches the HTML content for a single page.
    """
    query_path = project_root / "queries" / "get_page.gql"
    with open(query_path, "r") as f:
        query = f.read()

    variables = {"path": path, "locale": "en"}

    response = run_graphql_query(query, variables)
    page_data = response.get("data", {}).get("pages", {}).get("singleByPath", {})

    if not page_data:
        print(f"Warning: No content returned for {path}")
        return {"title": "", "content": ""}

    return {
        "title": page_data.get("title", "Untitled"),
        "content": page_data.get("content", "") or "",
    }


def fix_internal_links(html_content):
    """
    Converts web links (e.g. /en/knowledge-area-1) to internal anchors (#knowledge-area-1).
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Look for links that start with /en/ or just / (depending on wiki config)
    for a in soup.find_all("a", href=True):
        href = a["href"]

        # Check if it is a local wiki link
        if "/en/" in href:
            # Extract the slug: http://wiki.com/en/my-slug -> my-slug
            # OR /en/my-slug -> my-slug
            clean_slug = href.split("/en/")[-1]

            # Remove any query params or hashes that might already exist
            clean_slug = clean_slug.split("?")[0].split("#")[0].rstrip("/")

            # Point to the internal ID
            a["href"] = f"#{clean_slug}"

    return str(soup)


def clean_html_content(html_content):
    """
    Removes web-only artifacts like navigation bars and redundant TOCs.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove the "Subsections" mini-TOC found on parent pages
    # Look for the specific <h2>Subsections:</h2> injected by the populator
    for h2 in soup.find_all("h2", string="Subsections:"):
        # Remove the <ul> that immediately follows it
        next_sibling = h2.find_next_sibling()
        if next_sibling and next_sibling.name == "ul":
            next_sibling.decompose()
        # Remove the header itself
        h2.decompose()

    # Remove "Previous / Next" Navigation Links
    for div in soup.find_all("div"):
        text = div.get_text()
        if "←" in text or "→" in text:
            # Check if it looks like a nav bar (contains links)
            if div.find("a"):
                div.decompose()

    # Remove all horizontal rules <hr>
    for hr in soup.find_all("hr"):
        hr.decompose()

    return str(soup)


def process_footnotes(html_content, global_counter, chapter_buffer):
    """
    Renumbers footnotes in the HTML to match the global_counter.
    Extracts definitions into chapter_buffer.
    Returns: (cleaned_html, next_counter_value)
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Find all footnote links: <a href="#footnote-1" id="footnote-ref-1">[1]</a>
    # Look for links where href starts with #footnote-
    footnote_links = soup.find_all("a", href=re.compile(r"^#footnote-\d+$"))

    # Map old id, local to page, to new global id
    id_map = {}

    for link in footnote_links:
        old_href = link["href"]  # e.g. "#footnote-1"
        old_id = old_href.replace("#footnote-", "")

        if old_id not in id_map:
            id_map[old_id] = global_counter
            global_counter += 1

        new_id = id_map[old_id]

        # Update the link
        link["href"] = f"#footnote-{new_id}"
        link["id"] = f"footnote-ref-{new_id}"
        link.string = f"[{new_id}]"

    # Find and extract the definitions
    # Usually in an <ol> at the bottom
    # Look for <li id="footnote-1">

    for old_id, new_id in id_map.items():
        definition = soup.find("li", id=f"footnote-{old_id}")
        if definition:
            # Update ID
            definition["id"] = f"footnote-{new_id}"

            # Find the back link (arrow) and update it
            back_link = definition.find("a", href=f"#footnote-ref-{old_id}")
            if back_link:
                back_link["href"] = f"#footnote-ref-{new_id}"

            # Add to buffer
            chapter_buffer.append(str(definition))

            # Remove from the page content (we will re-add at end of chapter)
            definition.decompose()

    # Clean up empty footnote lists (optional, if the HTML leaves empty <ol>s)
    for footnotes_list in soup.find_all("ol", class_="footnotes-list"):
        if not footnotes_list.find_all("li"):
            footnotes_list.decompose()

    # Remove the <hr> often associated with footnotes if it exists
    for hr in soup.find_all("hr", class_="footnotes-break"):
        hr.decompose()

    return str(soup), global_counter


def build_pdf():
    pages = fetch_ordered_pages()
    if not pages:
        print("No pages to process.")
        return

    full_html_parts = []

    # Track current state
    current_root_slug = None
    chapter_footnotes_buffer = []  # Stores <li> strings
    footnote_counter = 1

    progress_bar = tqdm(
        pages,
        unit="page",
        ncols=100,
        bar_format="{percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}",
    )

    for page in progress_bar:
        path = page["path"]

        root_slug = path.split("/")[0]

        # Chapter Change Detection
        if current_root_slug is not None and root_slug != current_root_slug:
            if chapter_footnotes_buffer:
                footnotes_html = (
                    '<div class="chapter-footnotes">'
                    "<h3>Chapter References</h3>"
                    "<ol>" + "".join(chapter_footnotes_buffer) + "</ol>"
                    "</div>"
                )
                full_html_parts.append(footnotes_html)
                chapter_footnotes_buffer = []

            footnote_counter = 1

        current_root_slug = root_slug

        # Fetch Content
        page_data = get_page_content(path)
        raw_content = page_data["content"]
        page_title = page_data["title"]

        # Header Logic
        depth = path.count("/")
        header_level = min(depth + 1, 6)

        title_html = (
            f'<div id="{path}"><h{header_level}>{page_title}</h{header_level}></div>'
        )

        # Clean Content
        cleaned_body = clean_html_content(raw_content)

        # Combine
        combined_html = f"{title_html}\n{cleaned_body}"

        # Fix Internal Links (TOC and Cross-refs) <-- NEW STEP
        linked_html = fix_internal_links(combined_html)

        # Footnotes
        final_content, footnote_counter = process_footnotes(
            linked_html, footnote_counter, chapter_footnotes_buffer
        )

        full_html_parts.append(
            f'<div class="wiki-page" id="{path}">{final_content}</div>'
        )

    # Final Flush
    # Append footnotes for the last chapter
    if chapter_footnotes_buffer:
        print(
            f"  -> Flushing {len(chapter_footnotes_buffer)} footnotes for final chapter"
        )
        footnotes_html = (
            '<div class="chapter-footnotes">'
            "<h3>Chapter References</h3>"
            "<ol>" + "".join(chapter_footnotes_buffer) + "</ol>"
            "</div>"
        )
        full_html_parts.append(footnotes_html)

    # --- Generate PDF ---
    progress_bar.close()
    print("Generating PDF...")
    full_body_html = "\n".join(full_html_parts)

    # Wrap in standard HTML5 boilerplate
    final_document = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>LEBOK Guide</title>
    </head>
    <body>
        {full_body_html}
    </body>
    </html>
    """

    HTML(string=final_document).write_pdf(OUTPUT_FILENAME, stylesheets=[PDF_CSS])
    print(f"Done! Saved to {OUTPUT_FILENAME}")


if __name__ == "__main__":
    build_pdf()
