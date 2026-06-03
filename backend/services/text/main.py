import spacy
import re
from faker import Faker
import sys

nlp = spacy.load("en_core_web_trf")  # transformer model
faker = Faker()

# === CONFIG ===
redaction_level = int(sys.argv[1]) 

ENTITY_LABELS_TO_REDACT = [
    "PERSON", "ORG", "GPE", "LOC", "DATE",
    "TIME", "NORP", "FAC"
]

patterns = {
    "EMAIL": r"\b[\w\.-]+@[\w\.-]+\.\w+\b",
    "PHONE": r"\b(?:\+91[-\s]?)?[6-9]\d{9}\b",
    "PAN": r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    "AADHAAR": r"\b\d{4}\s\d{4}\s\d{4}\b",
    "CREDIT_CARD": r"\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b"
}

# 🔥 Read from stdin if provided, else fallback to input.txt
if not sys.stdin.isatty():
    text = sys.stdin.read()
else:
    with open("input.txt", "r", encoding="utf-8") as f:
        text = f.read()

doc = nlp(text)

replacements = {}

def get_fake(label):
    if label == "PERSON":
        return faker.name()
    elif label in ["GPE", "LOC"]:
        return faker.city()
    elif label == "DATE":
        return faker.date()
    elif label == "ORG":
        return faker.company()
    elif label == "EMAIL":
        return faker.email()
    elif label == "PHONE":
        return faker.phone_number()
    else:
        return "[REDACTED]"

TITLES = ["Mr.", "Mrs.", "Ms.", "Dr.", "Adv.", "Shri", "Smt."]

spans = []

for ent in doc.ents:
    if ent.label_ in ENTITY_LABELS_TO_REDACT:
        start = ent.start_char
        end = ent.end_char

        for title in TITLES:
            title_with_space = title + " "
            title_start = start - len(title_with_space)

            if title_start >= 0 and text[title_start:start] == title_with_space:
                start = title_start
                break

        spans.append((start, end, text[start:end], ent.label_))

for label, pattern in patterns.items():
    for match in re.finditer(pattern, text):
        spans.append((match.start(), match.end(), match.group(), label))

spans = sorted(spans, key=lambda x: x[0], reverse=True)

redacted_text = text
 
for start, end, original, label in spans:
    if original not in replacements:
        if redaction_level == 1:
            replacements[original] = "[REDACTED]"
        elif redaction_level == 2:
            replacements[original] = get_fake(label)

    replacement = replacements[original]

    redacted_text = (
        redacted_text[:start] +
        replacement +
        redacted_text[end:]
    )

# If running standalone → save file
if sys.stdin.isatty():
    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(redacted_text)
    print("✅ Redaction complete. Output saved to output.txt")
else:
    # 🔥 When called from Node → just print result
    print(redacted_text)
