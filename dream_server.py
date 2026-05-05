import os
import sys
import re
import requests
import random
import time
import json
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response
import xml.etree.ElementTree as ET
try:
    import psycopg2
    from psycopg2.extras import DictCursor
    DB_TYPE = "postgres"
except ImportError:
    import sqlite3
    DB_TYPE = "sqlite"

# エンコーディング設定
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# .env読み込み（複数パスを試行）
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_paths = [
    os.path.join(base_dir, '.env'),
    os.path.join(base_dir, '..', '.env'),
    "C:\\Users\\dance\\Documents\\MEGA\\mcp\\.env"
]
for dotenv_path in dotenv_paths:
    load_dotenv(dotenv_path)
    if os.getenv("SAKURA_API_TOKEN"):
        break

TOKEN = os.getenv("SAKURA_API_TOKEN")
API_BASE = "https://api.ai.sakura.ad.jp/v1"
DB_PATH = os.path.join(base_dir, "yume.db")

# ---- 共通関数 ----
def get_db():
    if DB_TYPE == "postgres":
        url = os.getenv("DATABASE_URL")
        conn = psycopg2.connect(url, cursor_factory=DictCursor)
    else:
        conn = sqlite3.connect(DB_PATH)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute('''CREATE TABLE IF NOT EXISTS dreams
                     (id SERIAL PRIMARY KEY,
                      content TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      length INTEGER,
                      source TEXT DEFAULT 'ai',
                      seed_id INTEGER NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS seeds
                     (id SERIAL PRIMARY KEY,
                      content TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS dreams
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      content TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      length INTEGER,
                      source TEXT DEFAULT 'ai',
                      seed_id INTEGER NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS seeds
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      content TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def normalize_to_400(text):
    flat = re.sub(r'\s+', '', text)
    if len(flat) > 400:
        return flat[:400]
    if len(flat) < 400:
        return flat + '。' * (400 - len(flat))
    return flat

def generate_dream(seed_content=None):
    if not TOKEN:
        return None
    if seed_content:
        prompt = f"以下はユーザー提供の夢の種です：{seed_content}\n星新一風のSF短編（夢日記形式）を作成してください。400字原稿用紙に6割くらい埋める分量で、人間の欲望に関する奇抜でシュールな内容にしてください。"
    else:
        prompt = "星新一風のSF短編（夢日記形式）を作成してください。400字原稿用紙に6割くらい埋める分量で、人間の欲望に関する奇抜でシュールな内容にしてください。テーマにとらわれず自由な発想で。"
    try:
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            json={
                "model": "gpt-oss-120b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "stream": False
            },
            timeout=30
        )
        if resp.status_code != 200:
            print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
            return None
        data = resp.json()
        if "choices" not in data:
            print(f"Unexpected response: {data}", file=sys.stderr)
            return None
        content = data["choices"][0]["message"]["content"]
        return normalize_to_400(content)
    except Exception as e:
        print(e, file=sys.stderr)
        return None

# データベース操作
def save_dream(content, source='ai', seed_id=None):
    conn = get_db()
    c = conn.cursor()
    length = len(content)
    if DB_TYPE == "postgres":
        c.execute("INSERT INTO dreams (content, length, source, seed_id) VALUES (%s, %s, %s, %s) RETURNING id",
                  (content, length, source, seed_id))
        dream_id = c.fetchone()[0]
    else:
        c.execute("INSERT INTO dreams (content, length, source, seed_id) VALUES (?, ?, ?, ?)",
                  (content, length, source, seed_id))
        dream_id = c.lastrowid
    conn.commit()
    conn.close()
    return dream_id

def save_seed(content):
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("INSERT INTO seeds (content) VALUES (%s) RETURNING id", (content,))
        seed_id = c.fetchone()[0]
    else:
        c.execute("INSERT INTO seeds (content) VALUES (?)", (content,))
        seed_id = c.lastrowid
    conn.commit()
    conn.close()
    return seed_id

def get_dream(dream_id):
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("SELECT id, content, created_at, length, source, seed_id FROM dreams WHERE id = %s", (dream_id,))
    else:
        c.execute("SELECT id, content, created_at, length, source, seed_id FROM dreams WHERE id = ?", (dream_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "content": row[1], "created_at": row[2], "length": row[3],
                "source": row[4], "seed_id": row[5]}
    return None

def get_all_dreams(limit=20, offset=0):
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("SELECT id, content, created_at, length, source FROM dreams ORDER BY id DESC LIMIT %s OFFSET %s", (limit, offset))
    else:
        c.execute("SELECT id, content, created_at, length, source FROM dreams ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "content": r[1], "created_at": r[2], "length": r[3], "source": r[4]} for r in rows]

def get_all_seeds():
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("SELECT id, content FROM seeds")
    else:
        c.execute("SELECT id, content FROM seeds")
    rows = c.fetchall()
    conn.close()
    return rows

# ---- Flaskアプリ ----
app = Flask(__name__)
init_db()

# レスポンスフォーマット
def format_response(data, format_type):
    if format_type == "xml":
        root = ET.Element("dreams")
        items = data if isinstance(data, list) else [data]
        for item in items:
            dream_elem = ET.SubElement(root, "dream")
            for key, val in item.items():
                child = ET.SubElement(dream_elem, key)
                child.text = str(val) if val is not None else ""
        return Response(ET.tostring(root, encoding="unicode"), mimetype="application/xml; charset=utf-8")
    elif format_type == "rss":
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "曇晴筆記 Yume Hyakuya"
        ET.SubElement(channel, "link").text = request.url_root
        ET.SubElement(channel, "description").text = "星新一風SF夢日記生成"
        items = data if isinstance(data, list) else [data]
        for item in items:
            item_elem = ET.SubElement(channel, "item")
            ET.SubElement(item_elem, "title").text = f"夢 #{item['id']}"
            ET.SubElement(item_elem, "description").text = item['content']
            ET.SubElement(item_elem, "pubDate").text = item['created_at']
            ET.SubElement(item_elem, "guid").text = f"{request.url_root}api/dream/{item['id']}"
        return Response(ET.tostring(rss, encoding="unicode"), mimetype="application/rss+xml; charset=utf-8")
    elif format_type == "txt":
        if isinstance(data, list):
            lines = [f"ID: {d['id']}\n{d['content']}\n{'='*40}" for d in data]
            return Response("\n".join(lines), mimetype="text/plain; charset=utf-8")
        else:
            return Response(data['content'], mimetype="text/plain; charset=utf-8")
    else:
        return jsonify(data)

# ルーティング
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/dream/random')
def random_dream():
    seed_id = request.args.get('seed_id')
    seed_content = None
    if seed_id:
        conn = get_db()
        c = conn.cursor()
        if DB_TYPE == "postgres":
            c.execute("SELECT content FROM seeds WHERE id = %s", (seed_id,))
        else:
            c.execute("SELECT content FROM seeds WHERE id = ?", (seed_id,))
        row = c.fetchone()
        conn.close()
        if row:
            seed_content = row[0]
    content = generate_dream(seed_content)
    if not content:
        return jsonify({"error": "夢の生成に失敗しました"}), 500
    source = 'seed' if seed_content else 'ai'
    dream_id = save_dream(content, source=source, seed_id=seed_id if seed_content else None)
    dream = get_dream(dream_id)
    fmt = request.args.get('format', 'json')
    return format_response(dream, fmt)

@app.route('/api/dreams')
def list_dreams():
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    dreams = get_all_dreams(limit=limit, offset=offset)
    fmt = request.args.get('format', 'json')
    return format_response(dreams, fmt)

@app.route('/api/dream/<int:dream_id>')
def get_dream_api(dream_id):
    dream = get_dream(dream_id)
    if not dream:
        return jsonify({"error": "夢が見つかりません"}), 404
    fmt = request.args.get('format', 'json')
    return format_response(dream, fmt)

@app.route('/api/seed/submit', methods=['POST'])
def submit_seed():
    content = request.form.get('content') or (request.json and request.json.get('content'))
    if not content:
        return jsonify({"error": "内容がありません"}), 400
    seed_id = save_seed(content)
    return jsonify({"id": seed_id, "content": content}), 201

@app.route('/api/seeds')
def list_seeds():
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("SELECT id, content, created_at FROM seeds ORDER BY id DESC")
    else:
        c.execute("SELECT id, content, created_at FROM seeds ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows])

@app.route('/dream.json')
def serve_dream_json():
    json_path = os.path.join(base_dir, 'dream.json')
    if not os.path.exists(json_path):
        return jsonify({"error": "dream.json not found"}), 404
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

@app.route('/raw')
def raw_dream():
    content = generate_dream()
    if not content:
        return "夢の生成に失敗しました", 500
    return Response(content, mimetype='text/plain; charset=utf-8')

# ---- コマンドライン機能 ----
def batch_generate(count=100):
    init_db()
    seeds = get_all_seeds()
    print(f"Found {len(seeds)} seeds.")
    for i in range(count):
        if i % 2 == 0 and seeds:
            seed_id, seed_content = random.choice(seeds)
            print(f"Generating dream {i+1}/{count} using seed #{seed_id}")
            content = generate_dream(seed_content)
            source = 'seed'
        else:
            print(f"Generating dream {i+1}/{count} (AI only)")
            content = generate_dream()
            source = 'ai'
            seed_id = None
        if content:
            dream_id = save_dream(content, source=source, seed_id=seed_id if source == 'seed' else None)
            print(f"  -> Saved as ID {dream_id}")
        else:
            print("  -> Failed")
        if i < count - 1:
            time.sleep(2)
    print(f"Done. {count} dreams generated.")

def single_generate():
    content = generate_dream()
    if content:
        print(content)
    else:
        print("夢の生成に失敗しました", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='夢日記生成・管理ツール')
    parser.add_argument('--serve', action='store_true', help='Flaskサーバーを起動（デフォルト）')
    parser.add_argument('--batch', type=int, metavar='N', help='N個の夢を一括生成')
    parser.add_argument('--single', action='store_true', help='単一の夢を生成して出力')
    parser.add_argument('--port', type=int, default=5000, help='Flaskサーバーのポート（デフォルト:5000）')
    args = parser.parse_args()

    if args.batch:
        batch_generate(args.batch)
    elif args.single:
        single_generate()
    else:
        print(f"Starting Flask server on port {args.port}...")
        app.run(host='0.0.0.0', port=args.port, debug=True)
