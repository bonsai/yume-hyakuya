import os
import json
import sys
from dotenv import load_dotenv

load_dotenv()

# Neon 接続情報
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("ERROR: DATABASE_URL not set", file=sys.stderr)
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import DictCursor
except ImportError:
    print("ERROR: psycopg2 not installed. pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

# JSON ファイルパス
base_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(base_dir, 'static', 'dream.json')

print(f"Reading {json_path}...")
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

dreams = data.get('dreams', [])
print(f"Found {len(dreams)} dreams in JSON")

# Neon に接続
print("Connecting to Neon...")
conn = psycopg2.connect(DB_URL, cursor_factory=DictCursor)
c = conn.cursor()

# 既存データをクリア（必要に応じてコメントアウト）
# c.execute("DELETE FROM dreams")
# conn.commit()
# print("Cleared existing dreams")

# データ挿入
inserted = 0
for d in dreams:
    content = d.get('text', '')
    if not content:
        continue
    length = len(content)
    source = d.get('source', 'initial')
    # created_at は JSON の date フィールドを使用、なければ現在時刻
    created_at = d.get('date', None)
    
    # 重複チェック（content で）
    c.execute("SELECT id FROM dreams WHERE content = %s", (content,))
    if c.fetchone():
        print(f"Skipping duplicate: {content[:30]}...")
        continue
    
    c.execute(
        "INSERT INTO dreams (content, length, source, created_at) VALUES (%s, %s, %s, %s)",
        (content, length, source, created_at)
    )
    inserted += 1
    if inserted % 10 == 0:
        print(f"Inserted {inserted}...")

conn.commit()
conn.close()
print(f"Done! Inserted {inserted} new dreams into Neon.")
