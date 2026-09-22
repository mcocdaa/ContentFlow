"""Inline-CSS HTML Formatter for WeChat Official Accounts.
Converts Markdown to beautiful, reader-friendly inline-styled HTML that can be
directly pasted or submitted via WeChat API without broken styles.
"""

import re
import html

THEMES = {
    "tech_blue": {
        "primary": "#2563eb",
        "secondary": "#3b82f6",
        "accent": "#0ea5e9",
        "bg_quote": "#eff6ff",
        "border_quote": "#3b82f6",
        "text_main": "#1f2937",
        "text_muted": "#4b5563",
        "code_bg": "#f1f5f9",
        "header_bg": "linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%)",
    },
    "emerald": {
        "primary": "#059669",
        "secondary": "#10b981",
        "accent": "#14b8a6",
        "bg_quote": "#ecfdf5",
        "border_quote": "#10b981",
        "text_main": "#1f2937",
        "text_muted": "#4b5563",
        "code_bg": "#f1f5f9",
        "header_bg": "linear-gradient(135deg, #064e3b 0%, #059669 100%)",
    },
}


def markdown_to_wechat_html(md_content: str, theme_name: str = "tech_blue") -> str:
    """Converts markdown text to WeChat inline-styled HTML."""
    theme = THEMES.get(theme_name, THEMES["tech_blue"])
    lines = md_content.splitlines()
    html_out = []

    # Container styling
    container_style = (
        "max-width: 680px; margin: 0 auto; padding: 20px 16px; "
        "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
        "'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; "
        f"font-size: 15px; line-height: 1.85; color: {theme['text_main']}; "
        "letter-spacing: 0.03em; word-break: break-word;"
    )

    html_out.append(f'<div class="wechat-article" style="{container_style}">')

    in_list = False
    in_code_block = False
    code_buffer = []

    for raw_line in lines:
        line = raw_line.strip()

        # Handle code block ```
        if line.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_buffer = []
                continue
            else:
                in_code_block = False
                code_text = html.escape("\n".join(code_buffer))
                pre_style = (
                    f"background: {theme['code_bg']}; padding: 14px 16px; "
                    "border-radius: 8px; overflow-x: auto; font-size: 13px; "
                    "font-family: 'Fira Code', Menlo, Monaco, Consolas, monospace; "
                    "margin: 16px 0; border: 1px solid #e2e8f0; line-height: 1.6;"
                )
                html_out.append(f'<pre style="{pre_style}"><code>{code_text}</code></pre>')
                continue

        if in_code_block:
            code_buffer.append(raw_line)
            continue

        # Close list if not a list item
        if in_list and not (line.startswith("- ") or line.startswith("* ") or re.match(r"^\d+\.\s", line)):
            html_out.append('</ul>')
            in_list = False

        # Empty line
        if not line:
            continue

        # Header 1
        if line.startswith("# "):
            title = html.escape(line[2:].strip())
            h1_style = (
                f"font-size: 22px; font-weight: 700; color: #ffffff; "
                f"background: {theme['header_bg']}; padding: 18px 20px; "
                "border-radius: 10px; margin: 24px 0 20px 0; text-align: center; "
                "box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);"
            )
            html_out.append(f'<h1 style="{h1_style}">{title}</h1>')
            continue

        # Header 2
        if line.startswith("## "):
            title = html.escape(line[3:].strip())
            h2_style = (
                f"font-size: 18px; font-weight: 700; color: {theme['primary']}; "
                f"border-left: 4px solid {theme['primary']}; padding-left: 12px; "
                "margin: 28px 0 14px 0; display: flex; align-items: center;"
            )
            html_out.append(f'<h2 style="{h2_style}">{title}</h2>')
            continue

        # Header 3
        if line.startswith("### "):
            title = html.escape(line[4:].strip())
            h3_style = (
                f"font-size: 16px; font-weight: 600; color: #334155; "
                "margin: 20px 0 10px 0;"
            )
            html_out.append(f'<h3 style="{h3_style}">{title}</h3>')
            continue

        # Blockquote >
        if line.startswith("> "):
            quote_text = _format_inline(line[2:].strip(), theme)
            quote_style = (
                f"background: {theme['bg_quote']}; border-left: 4px solid {theme['border_quote']}; "
                "padding: 12px 16px; border-radius: 0 8px 8px 0; margin: 16px 0; "
                f"color: {theme['text_muted']}; font-size: 14px; font-style: normal;"
            )
            html_out.append(f'<blockquote style="{quote_style}">{quote_text}</blockquote>')
            continue

        # Bullet list
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_out.append('<ul style="padding-left: 20px; margin: 14px 0;">')
                in_list = True
            item_text = _format_inline(line[2:].strip(), theme)
            li_style = "margin-bottom: 8px; line-height: 1.7; color: #374151;"
            html_out.append(f'<li style="{li_style}">{item_text}</li>')
            continue

        # Regular Paragraph
        p_text = _format_inline(line, theme)
        p_style = "margin: 14px 0; text-align: justify; color: #374151; font-size: 15px;"
        html_out.append(f'<p style="{p_style}">{p_text}</p>')

    if in_list:
        html_out.append('</ul>')

    html_out.append('</div>')
    return "\n".join(html_out)


def _format_inline(text: str, theme: dict) -> str:
    """Formats inline bold, code, and links with inline CSS."""
    # Bold **text**
    text = re.sub(
        r"\*\*(.*?)\*\*",
        rf'<strong style="color: {theme["primary"]}; font-weight: 600;">\1</strong>',
        text,
    )
    # Inline code `code`
    text = re.sub(
        r"`(.*?)`",
        rf'<code style="background: {theme["code_bg"]}; color: #d97706; padding: 2px 6px; border-radius: 4px; font-size: 13px; font-family: monospace;">\1</code>',
        text,
    )
    return text
