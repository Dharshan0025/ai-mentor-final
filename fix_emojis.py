import codecs
import re

path = r"d:\Ai-mentor\frontend\src\pages\Tutor\Tutor.jsx"
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

text = re.sub(r"icon:\s*'.*?',\s*desc:\s*'Key points & tips'", "icon: '📝', desc: 'Key points & tips'", text)
text = re.sub(r"icon:\s*'.*?',\s*desc:\s*'Diagrams & examples'", "icon: '🎨', desc: 'Diagrams & examples'", text)
text = re.sub(r"icon:\s*'.*?',\s*desc:\s*'Step-by-step reasoning'", "icon: '🧮', desc: 'Step-by-step reasoning'", text)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)

print("done")
