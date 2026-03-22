import codecs
import os

path = r"d:\Ai-mentor\frontend\src\pages\Tutor\Tutor.jsx"

replacements = {
    "â€”": "—",
    "â€¦": "…",
    "Â·": "·",
    "âœ✓": "✔", # Wait, the screenshot showed âœ" which is usually ✔
    "âœ“": "✔",
    "â”€": "—",
    "âœ•": "✖",
    "ðŸŽ¨": "🎨",
    "ðŸ§®": "🧮",
    "ðŸ“ ": "📝",
    "ðŸŽ­": "🎬",
    "ðŸ“Œ": "📌",
    "ðŸ”§": "🔧",
    "â “": "❓",
    "ðŸ’¡": "💡",
}

# The user screenshot showed "âœ\" Quiz" (it might be "âœ" or "âœ✓")
# Let's check the exact string in the file again for line 316.

with codecs.open(path, 'r', 'utf-8') as f:
    content = f.read()

# Manual cleanup for common patterns
content = content.replace("â€”", "—")
content = content.replace("â€¦", "…")
content = content.replace("Â·", "·")
content = content.replace("âœ“", "✔")
content = content.replace("âœ”", "✔")
content = content.replace("âœ\" ", "✔ ") # common corruption for checkmark
content = content.replace("âœ\"", "✔") # common corruption for checkmark
content = content.replace("â”€", "—")
content = content.replace("â ¸", "⌃")
content = content.replace("âœ•", "✖")

# Redo emojis just in case
content = content.replace("ðŸŽ¨", "🎨")
content = content.replace("ðŸ§®", "🧮")
content = content.replace("ðŸ“ ", "📝")
content = content.replace("ðŸŽ­", "🎬")
content = content.replace("ðŸ“Œ", "📌")
content = content.replace("ðŸ”§", "🔧")
content = content.replace("â “", "❓")
content = content.replace("ðŸ’¡", "💡")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(content)

print("done fixing Tutor.jsx")
