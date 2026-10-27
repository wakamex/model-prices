"""Fixtures rendered in the HTML layouts that pages now serve."""

import re

def as_html(markdown: str) -> str:
    """A Markdown docs fixture rendered as the HTML Alibaba's .md addresses serve since
    2026-10-27: # headings as <hN>, each <Tab> as a section under an <h4>, list items as
    <li>, and other text lines as paragraphs."""
    lines = ["<!DOCTYPE html><html><body>"]
    for line in markdown.splitlines():
        text = line.strip()
        heading = re.match(r"(#{1,6}) (.*?)(?: <span[^>]*/>)?$", text)
        tab = re.match(r'<Tab title="([^"]*)">$', text)
        if heading:
            lines.append(f"<h{len(heading.group(1))} id=\"x\">{heading.group(2)}</h{len(heading.group(1))}>")
        elif tab:
            lines.append(f'<section><h4 id="x">{tab.group(1)}</h4>')
        elif text == "</Tab>":
            lines.append("</section>")
        elif text in ("<Tabs>", "</Tabs>") or text.startswith(("{/*", "<!--")):
            continue
        elif text.startswith("- "):
            lines.append(f"<ul><li>{text[2:]}</li></ul>")
        elif text and not text.startswith("<") and not text.startswith(">"):
            lines.append(f"<p>{text}</p>")
        else:
            lines.append(line)
    return "\n".join(lines + ["</body></html>"])
