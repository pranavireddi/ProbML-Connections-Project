import nltk
import json
import random
from nltk.corpus import cmudict
from english_words import get_english_words_set

# Load NLTK resources
nltk.download('cmudict')
PRON_DICT = cmudict.dict()

# 1. Load 20k Common English Words
# Using 'gcide' or similar frequency lists ensures words are "NYT-appropriate"
common_words = get_english_words_set(['web2'], alpha=True, lower=True)
# Filter: Only keep words in both common_words and CMUDict
valid_pool = [w for w in common_words if w in PRON_DICT and 3 <= len(w) <= 10]

class PhoneticEngine:
    @staticmethod
    def get_phones(word):
        return PRON_DICT[word.lower()][0] # Taking the first pronunciation

    @staticmethod
    def is_silent(word, letter, phoneme):
        """Checks if a letter is present but its corresponding sound is not."""
        phones = PhoneticEngine.get_phones(word)
        # Simple heuristic: if 'p' is in word but 'P' not in phones
        return letter in word.lower() and phoneme not in [p.strip('012') for p in phones]

    @staticmethod
    def is_true_silent_g(word):
        word = word.lower()
        if 'g' not in word:
            return False
        
        phones = [p.strip('012') for p in PhoneticEngine.get_phones(word)]
        
        # It's only silent if it doesn't make a Hard G (/G/) OR a Soft G (/JH/)
        # and isn't part of an 'NG' /ng/ sound (like "Blinking")
        sounds_to_exclude = {'G', 'JH', 'NG'}
        
        if not any(s in phones for s in sounds_to_exclude):
            return True
        return False

    @staticmethod
    def check_que_k(word):
        """'QUE' as 'K' sound at the end (Boutique, Antique)"""
        if word.lower().endswith('que'):
            return PhoneticEngine.get_phones(word)[-1] == 'K'
        return False

    @staticmethod
    def check_s_zh(word):
        """'S' or 'SI' making /ZH/ sound (Vision, Pleasure)"""
        word = word.lower()
        phones = PhoneticEngine.get_phones(word)
        # 1. Must contain the /ZH/ sound
        # 2. Must contain 's' (covers vision, pleasure, decision)
        # 3. Exclude 'z' (excludes azure, seizure) and 'j' (excludes beige)
        if 'ZH' in phones:
            if 's' in word and 'z' not in word and 'j' not in word:
                return True
        return False

    @staticmethod
    def check_hidden_y(word):
        """'Y' making the 'I' sound /AY/ (Sky, Type, Fly)"""
        if 'y' in word.lower():
            phones = PhoneticEngine.get_phones(word)
            return 'AY' in [p.strip('012') for p in phones]
        return False

# 2. Build the Buckets
buckets = {
    "Silent 'P'": [],
    "Silent 'K'": [],
    "Silent 'B'": [],
    "Silent 'G'": [],
    "Silent 'L'": [],
    "Ending 'QUE' sounds like 'K'": [],
    "S/SI makes ZH sound": [],
    "Words where 'Y' makes a long 'I' sound": [],
    "Silent 'H' at start": []
}

# 3. Categorize the 20k words
for word in valid_pool:
    if PhoneticEngine.is_silent(word, 'p', 'P'): buckets["Silent 'P'"].append(word)
    if PhoneticEngine.is_silent(word, 'k', 'K'): buckets["Silent 'K'"].append(word)
    if PhoneticEngine.is_silent(word, 'b', 'B'): buckets["Silent 'B'"].append(word)
    if PhoneticEngine.is_true_silent_g(word): buckets["Silent 'G'"].append(word)
    if PhoneticEngine.is_silent(word, 'l', 'L'): buckets["Silent 'L'"].append(word)
    if word.lower().startswith('h') and PhoneticEngine.is_silent(word, 'h', 'HH'): 
        buckets["Silent 'H' at start"].append(word)
    
    if PhoneticEngine.check_que_k(word): buckets["Ending 'QUE' sounds like 'K'"].append(word)
    if PhoneticEngine.check_s_zh(word): buckets["S/SI makes ZH sound"].append(word)
    if PhoneticEngine.check_hidden_y(word): buckets["Words where 'Y' makes a long 'I' sound"].append(word)

# 4. Generate 1,500 Groupings
all_groups = []
target = 2500

while len(all_groups) < target:
    # Pick a random bucket that has at least 4 words
    cat_name = random.choice(list(buckets.keys()))
    if len(buckets[cat_name]) >= 4:
        # Sample 4 unique words
        members = random.sample(buckets[cat_name], 4)
        all_groups.append({
            "group": cat_name,
            "members": [m.capitalize() for m in members]
        })

# 5. Output to JSON
with open('phonetic_connections.json', 'w') as f:
    json.dump(all_groups, f, indent=2)

print(f"Successfully generated {len(all_groups)} groupings.")