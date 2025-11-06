#!/usr/bin/env python

from typing import Dict, List, Any
import mammoth
import re
from bs4 import BeautifulSoup, NavigableString, Tag
import os
from dotenv import load_dotenv

load_dotenv()

LOCALE = os.getenv("WIKI_LOCALE")
WIKI_URL = os.getenv("WIKI_URL")


def create_slug(text: str) -> str:
    """
    Converts a string into a URL-friendly slug.
    """
    # Replace periods with hyphens
    text = text.replace(".", "-")

    # Convert to lowercase
    text = text.lower()

    # Remove all characters that are not letters, numbers, or spaces
    text = re.sub(r"[^a-z0-9\s-]", "", text)

    # Replace one or more spaces with a single hyphen
    text = re.sub(r"\s+", "-", text)

    return text


def extract_reference_code(text: str) -> str:
    """Extracts the leading reference code (e.g., '1.3.5') from a title."""
    if not text:
        return ""
    # Matches a pattern of digits and periods at the start of the string,
    # followed by optional whitespace.
    match = re.match(r"^([\d\.]+)\s*", text)
    if match:
        return match.group(1).strip()
    return ""


def build_nested_toc(nodes: List[Dict[str, Any]]) -> str:
    """
    Recursively generates a nested <ul> list of ToC links based on
    the hierarchy (parent/child relationship) of the nodes.
    """
    if not nodes:
        return ""

    html = ['<ul style="list-style-type: none; padding-left: 1.5em;">']
    for node in nodes:
        title = node.get("title")
        slug = node.get("slug")

        # Skip nodes that lack a title or slug (like the TOC node itself)
        if not title or not slug:
            continue

        # Build the href
        href = f"{WIKI_URL}/{LOCALE}/{slug}"

        # Build the list item
        html.append(f'<li style="margin-bottom: 1em;"><a href="{href}">{title}</a>')

        # Recursively call for children to create the nested <ul>
        if node["children"]:
            html.append(build_nested_toc(node["children"]))

        # Close the list item
        html.append("</li>")

    html.append("</ul>")
    return "\n".join(html)


def convert_docx_to_html(filepath: str) -> str:
    """Converts a DOCX file to HTML"""
    style_map = "p[style-name='Title'] => title-tag:fresh"

    with open(filepath, "rb") as docx_file:
        result = mammoth.convert_to_html(docx_file, style_map=style_map)
        # result = mammoth.convert_to_html(docx_file)
        html_text = result.value

        # Debugging: Print the raw output *before* parsing
        # print("\n--- RAW MAMMOTH OUTPUT ---")
        # print(html_text)
        # print("--- END RAW OUTPUT ---\n")
        # ---

        return html_text


def extract_footnotes(html_text: str) -> tuple[dict, str]:
    """
    Finds all footnote definitions, returns them as a dictionary,
    removes them from the main text
    """
    soup = BeautifulSoup(html_text, "html.parser")

    # Pattern for footnote tags (like <li id="footnote-1">)
    pattern = re.compile(r"^footnote-(\w+)$")
    all_footnotes = {}

    footnote_list_items = soup.find_all("li", id=pattern)

    if not footnote_list_items:
        # No footnotes found
        return {}, html_text

    for li in footnote_list_items:
        note_id_match = pattern.match(li["id"])
        if note_id_match:
            note_id = note_id_match.group(1)

            # Remove the back arrow link
            back_arrow = li.find("a", href=re.compile(r"^#footnote-ref-"))
            if back_arrow:
                back_arrow.decompose()

            # Store the inner html of the <li> tag
            all_footnotes[note_id] = li.decode_contents().strip()

    # Remove the entire parent list from the document
    if footnote_list_items:
        footnote_list_items[0].parent.decompose()

    return all_footnotes, str(soup)


def inject_html_footnotes(nodes: List[Dict[str, Any]], all_footnotes: dict):
    """
    Walks the document tree, finds all footnote references
    anand converts appends a new HTML list of definitions
    """
    # Find Mammoth's HTML footnote reference
    # Like <a href="#footnote-1" id="footnote-ref-1">...</a>
    html_ref_pattern = re.compile(r'<a href="#footnote-(\w+)" id="footnote-ref-\d+">')

    for node in nodes:
        if node["content"]:
            used_ids = set()

            # Find all unique footnote IDs in the section
            for match in html_ref_pattern.finditer(node["content"]):
                note_id = match.group(1)
                if note_id:
                    used_ids.add(note_id)

            # Append HTML definitions for any footnotes found
            if used_ids:
                # Build an HTML block for the definitions
                definitions_html = [
                    '<hr class="footnotes-break">',
                    '<ol class="footnotes-list">',
                ]

                # sort IDs for consistent order
                for note_id in sorted(
                    list(used_ids), key=lambda x: int(x) if x.isdigit() else x
                ):
                    # Get the inner HTML of the note stored earlier
                    note_html = all_footnotes.get(
                        note_id, f"Footnote '{note_id}' not found."
                    )

                    # Recreate the <li> tag with the original ID
                    definitions_html.append(
                        f'<li id="footnote-{note_id}">{note_html}</li>'
                    )

                definitions_html.append("</ol>")
                definitions_block = "\n".join(definitions_html)

                # Append the HTML block to the end of the section's content
                node["content"] = f"{node['content'].strip()}\n\n{definitions_block}"

        # Now do it again for child nodes
        if node["children"]:
            inject_html_footnotes(node["children"], all_footnotes)


def parse_document_tree(html_text: str) -> List[Dict[str, Any]]:
    """
    Splits HTML document text into a tree based on headings.
    Node content is stored as an HTML string.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    document_tree: List[Dict[str, Any]] = []
    parents_stack: List[Dict[str, Any]] = []

    last_node = None
    current_content_buffer: List[str] = []  # Stores HTML strings

    heading_tags = re.compile(r"^h([1-6])$")

    # Define the flush function
    def flush_buffer_to_node():
        nonlocal last_node
        if last_node and current_content_buffer:
            content = "".join(current_content_buffer).strip()
            content = re.sub(r"(\n\s*){2,}", "\n\n", content)  # Clean up newlines
            last_node["content"] = content
            current_content_buffer.clear()

    # Iterate over all direct children of the <body> tag
    root_element = soup.body if soup.body else soup
    body_content = root_element.contents

    for element in body_content:
        if isinstance(element, Tag):
            is_heading = False
            level = -1
            title = ""
            match = heading_tags.match(element.name)

            # Case 1: It's a heading tag (<h1>...<h6>)
            if match:
                is_heading = True
                level = int(match.group(1))
                title = element.get_text().strip()

            # elif element.name == "title-tag":
            #     is_heading = True
            #     title = element.get_text().strip()
            #
            #     if not parents_stack:
            #         level = 1
            #     else:
            #         level = parents_stack[-1]["level"] + 1

            if is_heading:
                flush_buffer_to_node()

                if not title:
                    continue  # Skip empty headings

                # Get the slug for this node
                current_slug = create_slug(title)
                parent_slug = ""

                # Find the parent
                while parents_stack and parents_stack[-1]["level"] >= level:
                    parents_stack.pop()

                if parents_stack:
                    parent_slug = parents_stack[-1]["slug"]

                # Create the full page path
                full_path = ""
                if parent_slug:
                    full_path = f"{parent_slug}/{current_slug}"
                else:
                    full_path = current_slug

                new_node = {
                    "title": title,
                    "level": level,
                    "slug": full_path,
                    "content": "",
                    "children": [],
                }

                # while parents_stack and parents_stack[-1]["level"] >= level:
                #     parents_stack.pop()

                if not parents_stack:
                    document_tree.append(new_node)
                else:
                    parents_stack[-1]["children"].append(new_node)

                parents_stack.append(new_node)
                last_node = new_node

            # Case 2: It's a content tag (e.g., <p>, <ul>)
            elif last_node:
                # Append the HTML string of the tag to the buffer
                current_content_buffer.append(str(element))

        # Case 3: It's text content (NavigableString)
        elif isinstance(element, NavigableString) and last_node:
            if element.string.strip():
                current_content_buffer.append(element.string)

    # Flush content for the very last section
    flush_buffer_to_node()

    return document_tree


def get_sections(filepath: str) -> List[Dict[str, Any]]:
    """
    Returns document content split by headings into a tree.
    The content of each node is an HTML string
    """
    html_text = convert_docx_to_html(filepath)
    footnotes, cleaned_html = extract_footnotes(html_text)
    sections = parse_document_tree(cleaned_html)

    # slug_map = build_slug_map(sections)
    #
    # clean_toc(sections, slug_map)

    nested_toc_html = build_nested_toc(sections)
    for node in sections:
        if node["title"] == "Contents":
            node["content"] = nested_toc_html
            break

    if footnotes:
        inject_html_footnotes(sections, footnotes)

    return sections


def print_html_sections(nodes: List[Dict[str, Any]]):
    """
    Recursively prints the HTML document tree.
    """
    for node in nodes:
        level = node["level"]
        title_text = node["title"]

        if level == 0:
            # It's the <doc-title> special case
            print(f"<h1>{title_text}</h1>\n")
        else:
            print(f"<h{level}>{title_text}</h{level}>\n")

        # Print the current section's HTML
        if node["content"]:
            print(f"{node['content']}\n")

        # Recursive call for node children
        if node["children"]:
            print_html_sections(node["children"])


if __name__ == "__main__":
    filepath = "lebok.docx"
    sections = get_sections(filepath)

    def print_tree(nodes: List[Dict[str, Any]], indent: str = ""):
        for node in nodes:
            print(f"{indent}- {node['title']} (Level {node['level']})")
            if node["content"]:
                # Print a preview of the content (once)
                print(f"{indent}  Content: '{node['content'][:50].strip()}...'")
            if node["children"]:
                print_tree(node["children"], indent + "  ")

    print_tree(sections)
    # print_html_sections(sections)
