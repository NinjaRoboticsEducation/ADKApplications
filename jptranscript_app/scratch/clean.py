import re
import sys

def clean_transcript(text):
    # Remove initial quote if any
    text = text.strip('”"')
    
    # Remove timestamps like '0:08', '11:16', etc on their own line
    text = re.sub(r'^\d+:\d+\n', '', text, flags=re.MULTILINE)
    
    # Remove spaces between Japanese characters (fullwidth and halfwidth spaces)
    text = re.sub(r'(?<=[ぁ-んァ-ン一-龥々])[\s\u3000]+(?=[ぁ-んァ-ン一-龥々、。！？])', '', text)
    text = re.sub(r'(?<=[、。！？])[\s\u3000]+(?=[ぁ-んァ-ン一-龥々])', '', text)
    text = text.replace(' ', '')
    
    # Replace newlines for cleaner processing, or just keep them
    # We will keep newlines to keep text readable
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    cleaned_lines = []
    for line in lines:
        line = re.sub(r'^(はい。|まあ、|えっと、|ええ、|あの、|あの|で、|じゃあ、|で|まあ)', '', line)
        line = re.sub(r'^(はい。|まあ、|えっと、|ええ、|あの、|あの|で、|じゃあ、|で|まあ)', '', line)
        line = re.sub(r'^ということで、', 'ということで、', line)
        if line:
            cleaned_lines.append(line)
            
    # Additional AI cleanup will be needed based on the rules, but this pre-cleans the mechanical issues.
    return '\n'.join(cleaned_lines)

with open('scratch/input.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

cleaned = clean_transcript(raw)

with open('scratch/step1_mechanical.txt', 'w', encoding='utf-8') as f:
    f.write(cleaned)
