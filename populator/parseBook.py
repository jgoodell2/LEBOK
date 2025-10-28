#!/usr/bin/env python

from typing import Dict, List, Any
import mammoth
import re


def convert_docx_to_md(filepath: str) -> str:
    """Converts a DOCX file to Markdown"""
    style_map = "p[style-name='Title'] => text:fresh"
    # style_map = "p => debug-p:fresh"
    with open(filepath, "rb") as docx_file:
        # result = mammoth.convert_to_markdown(docx_file, style_map=style_map)
        result = mammoth.convert_to_markdown(docx_file)
        markdown_text = result.value
        # Let's print the raw output *before* parsing
        print("\n--- RAW MAMMOTH OUTPUT ---")
        print(markdown_text)
        print("--- END RAW OUTPUT ---\n")
        # ---
        return markdown_text


def strip_html_tags(text: str) -> str:
    """Removes HTML tags and preserve inner text"""
    return re.sub(r"<[^>]+>", "", text)


def clean_heading_text(text: str) -> str:
    # Unescape periods
    text = re.sub(r"\\(.)", r"\1", text)

    text = text.strip()

    # Strip markdown from the title
    while True:
        stripped = False
        if (text.startswith("__") and text.endswith("__")) or (
            text.startswith("**") and text.endswith("**")
        ):
            if len(text) > 4:  # Make sure it's not just "__"
                text = text[2:-2].strip()
                stripped = True
            else:
                break  # Stop if we just have "__" or "****"
        elif (text.startswith("*") and text.endswith("*")) or (
            text.startswith("_") and text.endswith("_")
        ):
            if len(text) > 2:  # Make sure it's not just "_"
                text = text[1:-1].strip()
                stripped = True
            else:
                break  # Stop if we just have "_" or "*"

        # If we didn't strip anything this pass, we're done.
        if not stripped:
            break

    return text.strip()


def extract_footnotes(md_text: str) -> tuple[dict, str]:
    """
    Finds all footnote definitions, returns them as a dictionary,
    removes them from the main text
    """
    # Pattern for standard Markdown footnote, e.g., [^1]: Some text
    std_pattern = re.compile(r"^\[\^(\w+)\]:\s*(.*)", re.MULTILINE)

    # Pattern for Mammoth's HTML anchor style, e.g., "1. <a...></a> text"
    mammoth_anchor_pattern = re.compile(
        r'^(\d+)\.\s*<a id="footnote-\d+"></a>\s*(.*)', re.MULTILINE
    )

    std_footnotes = dict(std_pattern.findall(md_text))
    anchor_footnotes = dict(mammoth_anchor_pattern.findall(md_text))

    all_footnotes = {**anchor_footnotes, **std_footnotes}

    # Clean up the back-arrow link that mammoth adds to definitions
    for note_id, note_text in all_footnotes.items():
        all_footnotes[note_id] = re.sub(
            r"\s*\[↑\]\(#footnote-ref-\d+\)$", "", note_text
        ).strip()

    # Remove all definitions from the text
    cleaned_md = std_pattern.sub("", md_text).strip()
    cleaned_md = mammoth_anchor_pattern.sub("", cleaned_md).strip()

    return all_footnotes, cleaned_md


def inject_md_footnotes(nodes: List[Dict[str, Any]], all_footnotes: dict):
    """
    Walks the document tree, finds all footnote references (standard,
    hyperlink-style, and superscript-style), and converts them to Markdown abbreviations.
    """
    # This pattern captures various footnote reference styles.
    # It finds: 1. [^id], 2. [[1]](...), 3. <sup>1</sup>
    reference_pattern = re.compile(
        r"\[\^(\w+)\]|"  # Group 1: Standard Markdown ref [^1]
        r'(?:<a id="footnote-ref-\d+"></a>)?\[\\?\[(\d+)\\?\]]\(#footnote-\d+\)|'  # Group 2: Hyperlink ref
        r"<sup>(\d+)</sup>"  # Group 3: HTML superscript ref
    )

    for node in nodes:
        if node["content"]:
            used_ids = set()

            # First pass: find all unique footnote IDs used in this section's content
            for match in reference_pattern.finditer(node["content"]):
                note_id = match.group(1) or match.group(2) or match.group(3)
                if note_id:
                    used_ids.add(note_id)

            # If footnotes were found, standardize references and append definitions
            if used_ids:
                # Define a replacer function to standardize all formats to [^id]
                def replacer(match):
                    note_id = match.group(1) or match.group(2) or match.group(3)
                    return f"[^{note_id}]" if note_id else match.group(0)

                # Replace all varied footnote formats with the standard one
                node["content"] = reference_pattern.sub(replacer, node["content"])

                grouping_pattern = r"(\[\^\w+\]),(?=\s*\[\^\w+\])"
                node["content"] = re.sub(grouping_pattern, r"\1ʻ", node["content"])

                # Build a block of standard Markdown footnote definitions
                definitions = []
                # Sort IDs to maintain a consistent order (numeric sorting for digits)
                for note_id in sorted(
                    list(used_ids), key=lambda x: int(x) if x.isdigit() else x
                ):
                    note_text = all_footnotes.get(
                        note_id, f"Footnote '{note_id}' not found."
                    )
                    definitions.append(f"[^{note_id}]: {note_text}")

                definitions_block = "\n".join(definitions)

                # Append the definitions to the end of the section's content
                node["content"] = f"{node['content'].strip()}\n\n{definitions_block}"

        # Recurse for children nodes
        if node["children"]:
            inject_md_footnotes(node["children"], all_footnotes)


def parse_document_tree(md_text: str) -> List[Dict[str, Any]]:
    """
    Splits markdown document text in a tree based on headings.

    Returns a list of sections:
    {
        'title': str,
        'level': int,
        'content': str,
        'children': List[Dict]
    }
    """
    document_tree: List[Dict[str, Any]] = []

    # Keep track of the current path in the tree
    parents_stack: List[Dict[str, Any]] = []

    current_content_buffer: List[str] = []
    last_node = None

    title_tag_pattern = re.compile(r"<doc-title>(.*?)</doc-title>", re.DOTALL)
    title_match = title_tag_pattern.search(md_text)

    if title_match:
        # Extract the title, remove the tag
        title_text = clean_heading_text(strip_html_tags(title_match.group(1)))
        md_text = title_tag_pattern.sub("", md_text).strip()

        if title_text:
            title_node = {
                "title": title_text,
                "level": 0,
                "content": "",
                "children": [],
            }

            document_tree.append(title_node)
            parents_stack.append(title_node)
            last_node = title_node

    heading_pattern = re.compile(r"^(#{1,6})\s+(.*)$")

    def flush_buffer_to_node():
        nonlocal last_node
        if last_node and current_content_buffer:
            content = "\n".join(current_content_buffer).strip()

            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
            last_node["content"] = "\n\n".join(paragraphs)
            current_content_buffer.clear()

    for line in md_text.splitlines():
        match = heading_pattern.match(line)

        if match:
            # If we've found a new heading, save the content for the previous one
            flush_buffer_to_node()

            # Heading level is the number of # symbols
            level = len(match.group(1))
            title = clean_heading_text(strip_html_tags(match.group(2).strip()))

            # Skip untitled sections rather than create a stub
            if not title:
                continue

            new_node = {
                "title": title,
                "level": level,
                "content": "",
                "children": [],
            }

            # Adjust the parent stack based on the new heading's level
            while parents_stack and parents_stack[-1]["level"] >= level:
                parents_stack.pop()

            # If the stack is empty, this is a top level heading_pattern
            if not parents_stack:
                document_tree.append(new_node)
            else:
                parents_stack[-1]["children"].append(new_node)

            parents_stack.append(new_node)
            last_node = new_node
        else:
            current_content_buffer.append(line)

    # Flush content for the very last section
    flush_buffer_to_node()

    return document_tree


def getSections(filepath: str) -> List[Dict[str, Any]]:
    """
    Returns document content split by headings into markdown paragraphs
    """
    md_text = convert_docx_to_md(filepath)
    # sections = split_by_headings(md_text)
    footnotes, cleaned_md = extract_footnotes(md_text)

    sections = parse_document_tree(cleaned_md)

    if footnotes:
        inject_md_footnotes(sections, footnotes)

    return sections


def print_markdown_document(nodes: List[Dict[str, Any]]):
    """
    Recursively prints the full Markdown document from the node tree.
    """
    for node in nodes:
        # Level 0 (Title) doesn't have a '#' in standard markdown,
        # but we'll use H1 for it.
        if node["level"] == 0:
            print(f"# {node['title']}\n")
        else:
            # Print the heading (e.g., '## My Title')
            heading_prefix = "#" * node["level"]
            print(f"{heading_prefix} {node['title']}\n")

        # Print the content for that section
        if node["content"]:
            print(f"{node['content']}\n")

        # Recursively print all children nodes
        if node["children"]:
            print_markdown_document(node["children"])


if __name__ == "__main__":
    filepath = "lebok.docx"
    sections = getSections(filepath)

    # for heading, paragraphs in sections.items():
    #     print(f"--- {heading} ---")
    #     for paragraph in paragraphs:
    #         print(paragraph)
    #         print()

    def print_tree(nodes: List[Dict[str, Any]], indent: str = ""):
        for node in nodes:
            print(f"{indent}- {node['title']} (Level {node['level']})")
            if node["content"]:
                # Print a preview of the content (once)
                print(f"{indent}  Content: '{node['content'][:50].strip()}...'")
            if node["children"]:
                print_tree(node["children"], indent + "  ")

    # print_tree(sections)
    print_markdown_document(sections)
