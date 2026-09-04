# backend/build_database.py
import json
import ast
from datasets import load_dataset
from markdownify import markdownify as md

def get_python_starter_code(code_def_str):
    try:
        definitions = ast.literal_eval(code_def_str)
        for lang_def in definitions:
            if lang_def.get('value') == 'python3':
                return lang_def.get('defaultCode', '')
        return "# No Python starter code found."
    except:
        return ""
def clean_topic(topic_str):
    try:
        if topic_str.startswith("["):
            tags = ast.literal_eval(topic_str)
            return tags[0] if tags else "General"
        return topic_str
    except:
        return "General"

def main():
    print("⏳ Downloading LeetCode dataset (Stream mode)...")
    
    try:
        ds = load_dataset("kaysss/leetcode-problem-detailed", split="train", streaming=True)
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # --- THE QUOTAS ---
    WANTED_TOPICS = ["Array", "String", "Tree", "Dynamic Programming", "Hash Table", "Linked List"]
    WANTED_DIFFICULTIES = ["Easy", "Medium", "Hard"]
    LIMIT_PER_BUCKET = 3  # 3 Easy, 3 Medium, 3 Hard per topic
    
    # Create a tracker: counts["Tree"]["Easy"] = 0
    counts = {t: {d: 0 for d in WANTED_DIFFICULTIES} for t in WANTED_TOPICS}
    
    final_questions = []
    seen_titles = set()
    total_collected = 0
    MAX_TOTAL = len(WANTED_TOPICS) * len(WANTED_DIFFICULTIES) * LIMIT_PER_BUCKET # 6 * 3 * 3 = 54
    
    print(f"🎯 Target: {LIMIT_PER_BUCKET} of each difficulty per topic (Total {MAX_TOTAL} questions).")
    print("🔄 Scanning...")

    for i, row in enumerate(ds):
        if total_collected >= MAX_TOTAL:
            print("✨ All quotas perfectly filled!")
            break
            
        # Scan deep (up to 4000) because "Hard" + "Tree" combinations can be rare
        if i > 4000: 
            print("⚠️ Scanned 4000 questions, stopping search.")
            break

        title = row.get('questionTitle')
        if title in seen_titles: continue
            
        # 1. CLEAN DATA
        raw_tags = row.get('topicTags', '')
        topic = clean_topic(raw_tags)
        difficulty = row.get('difficulty', 'Medium')
        
        # 2. CHECK IF WANTED
        if topic not in WANTED_TOPICS: continue
        if difficulty not in WANTED_DIFFICULTIES: continue
        
        # 3. CHECK QUOTA (The crucial step)
        if counts[topic][difficulty] >= LIMIT_PER_BUCKET:
            continue

        # 4. PROCESS CONTENT
        html_content = row.get('content', '')
        code_def = row.get('codeDefinition', '')
        starter_code = get_python_starter_code(code_def)
        
        if not html_content or "No Python" in starter_code:
            continue

        # 5. SAVE
        question_obj = {
            "id": row.get('questionFrontendId'),
            "title": title,
            "difficulty": difficulty,
            "topic": topic,
            "acRate": row.get('acRate', 'N/A'),
            "markdown_content": md(html_content, heading_style="ATX"),
            "starter_code": starter_code
        }
        
        final_questions.append(question_obj)
        seen_titles.add(title)
        
        # Update Counts
        counts[topic][difficulty] += 1
        total_collected += 1
        print(f"   [+1] {topic} - {difficulty}: {title}")

    # Save to JSON
    with open('questions.json', 'w', encoding='utf-8') as f:
        json.dump(final_questions, f, indent=2)
        
    print(f"\n✅ Success! Saved {len(final_questions)} balanced questions.")
    
    # Print Matrix to verify balance
    print("\n📊 Final Distribution:")
    headers = "".join([f"{d:>8}" for d in WANTED_DIFFICULTIES])
    print(f"{'TOPIC':<20} {headers}")
    for t in WANTED_TOPICS:
        row_str = "".join([f"{counts[t][d]:>8}" for d in WANTED_DIFFICULTIES])
        print(f"{t:<20} {row_str}")

if __name__ == "__main__":
    main()