import os
import sys
import re
import requests
import random
import time
import json
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from typing import List, Dict, Any
from email.utils import formatdate
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response, current_app
from flask_cors import CORS
import xml.etree.ElementTree as ET
import threading
try:
    import psycopg2
    from psycopg2.extras import DictCursor
    if os.getenv("DATABASE_URL"):
        DB_TYPE = "postgres"
    else:
        import sqlite3
        DB_TYPE = "sqlite"
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

# ---- メール送信関数 ----
def send_dream_email(dream_data):
    """生成された夢をメールで送信"""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    to_email = os.getenv("TO_EMAIL")
    
    if not all([smtp_user, smtp_pass, to_email]):
        print("Email settings incomplete, skipping email", file=sys.stderr)
        return False
    
    try:
        msg = MIMEText(f"夢ID: {dream_data['id']}\n日付: {dream_data['created_at']}\n文字数: {dream_data['length']}\n\n{dream_data['content']}")
        msg['Subject'] = Header(f"新しい夢日記 #{dream_data['id']}", 'utf-8')
        msg['From'] = smtp_user
        msg['To'] = to_email
        msg['Date'] = formatdate(localtime=True)
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"Email sent for dream {dream_data['id']}")
        return True
    except Exception as e:
        print(f"Email failed: {e}", file=sys.stderr)
        return False

# ---- 共通関数 ----
def get_db(db_path=None): # Add optional db_path argument
    if DB_TYPE == "postgres":
        url = os.getenv("DATABASE_URL")
        if not url:
            print("ERROR: DATABASE_URL is not set", file=sys.stderr)
            return None
        try:
            conn = psycopg2.connect(url, cursor_factory=DictCursor)
            return conn
        except Exception as e:
            print(f"DB connection failed: {e}", file=sys.stderr)
            return None
    else:
        if db_path:
            sqlite_db_path = db_path
        else:
            try:
                # Try to get DB_PATH from Flask config if in app context
                sqlite_db_path = current_app.config.get('DB_PATH', DB_PATH)
            except RuntimeError:
                # Fallback to global DB_PATH if outside app context
                sqlite_db_path = DB_PATH

        conn = sqlite3.connect(sqlite_db_path)
        conn.row_factory = sqlite3.Row  # Enable column name access
        return conn

def init_db(db_path=None):
    conn = get_db(db_path) # Pass db_path to get_db
    if not conn:
        print("ERROR: Failed to connect to database", file=sys.stderr)
        return
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute('''CREATE TABLE IF NOT EXISTS dreams
                     (id SERIAL PRIMARY KEY,
                      content TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      length INTEGER,
                      source TEXT DEFAULT 'ai',
                      seed_id INTEGER NULL,
                      is_read BOOLEAN DEFAULT FALSE)''')
        c.execute('''CREATE TABLE IF NOT EXISTS seeds
                     (id SERIAL PRIMARY KEY,
                      content TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        # 既存テーブルに列がなければ追加
        try:
            c.execute("ALTER TABLE dreams ADD COLUMN is_read BOOLEAN DEFAULT FALSE")
            conn.commit()  # Commit immediately after ALTER TABLE
        except Exception as e:
            print(f"PostgreSQL ALTER TABLE skipped (column exists?): {e}", file=sys.stderr)
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
        # SQLiteにis_read列を追加（既存テーブル用）
        try:
            c.execute("ALTER TABLE dreams ADD COLUMN is_read BOOLEAN DEFAULT 0")
            conn.commit()  # Commit immediately after ALTER TABLE
        except Exception as e:
            print(f"SQLite ALTER TABLE skipped (column exists?): {e}", file=sys.stderr)
    conn.commit()
    conn.close()

def load_initial_data():
    """Neonが空の場合、static/dream.json から初期データをロード"""
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("SELECT COUNT(*) FROM dreams")
    else:
        c.execute("SELECT COUNT(*) FROM dreams")
    count = c.fetchone()[0]
    if count > 0:
        conn.close()
        return
    # 空なら static/dream.json をロード
    try:
        static_path = os.path.join(base_dir, 'static', 'dream.json')
        with open(static_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        dreams = data.get('dreams', [])
        for d in dreams:
            content = d.get('text', '')
            length = len(content)
            source = 'initial'
            if DB_TYPE == "postgres":
                c.execute("INSERT INTO dreams (content, length, source) VALUES (%s, %s, %s)",
                          (content, length, source))
            else:
                c.execute("INSERT INTO dreams (content, length, source) VALUES (?, ?, ?)",
                          (content, length, source))
        conn.commit()
        print(f"Loaded {len(dreams)} initial dreams from static/dream.json")
    except Exception as e:
        print(f"Failed to load initial data: {e}", file=sys.stderr)
    conn.close()


def normalize_to_200(text):
    """Normalize text to exactly 200 characters"""
    if not text or not isinstance(text, str):
        return "夢の生成に失敗。再試行。" * 10  # Fallback text (20 chars * 10 = 200)
    flat = re.sub(r'\s+', '', text)
    if len(flat) > 200:
        return flat[:200]
    if len(flat) < 200:
        return flat + '。' * (200 - len(flat))
    return flat

def generate_dream(seed_content=None):
    if not TOKEN:
        return None
    if seed_content:
        prompt = f"以下はユーザー提供の夢の種です：{seed_content}\n星新一風のSF短編（夢日記形式）を作成してください。200字原稿用紙にぴったり収まる分量で、人間の欲望に関する奇抜でシュールな内容にしてください。"
    else:
        prompt = "星新一風のSF短編（夢日記形式）を作成してください。200字原稿用紙にぴったり収まる分量で、人間の欲望に関する奇抜でシュールな内容にしてください。テーマにとらわれず自由な発想で。"
    try:
        print(f"Making API request to: {API_BASE}/chat/completions", file=sys.stderr)
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            json={
                "model": "gpt-oss-120b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "stream": False
            },
            timeout=30
        )
        print(f"API Response Status: {resp.status_code}", file=sys.stderr)
        if resp.status_code != 200:
            print(f"Error {resp.status_code}: {resp.text}", file=sys.stderr)
            return None
        data = resp.json()
        print(f"API Response Data: {data}", file=sys.stderr)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            print(f"Unexpected response structure: {data}", file=sys.stderr)
            return None
        if not content:
            print(f"API returned None content, using fallback", file=sys.stderr)
            return "夢日記――今日、空から金の雨が降った。人々は歓声を上げるが、それはただの錯覚。本当の富は心の中にあった。欲望は満たされたが、何かが足りない。明日も夢を見よう。"
        return normalize_to_200(content)
    except Exception as e:
        print(f"Error in generate_dream: {e}", file=sys.stderr)
        return None

# データベース操作
def save_dream(content, source='ai', seed_id=None, db_path=None):
    conn = get_db(db_path) # Pass db_path to get_db
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

    # メール送信 (非同期)
    dream_data = get_dream(dream_id, db_path=db_path)
    if dream_data:
        email_thread = threading.Thread(target=send_dream_email, args=(dream_data,))
        email_thread.start()

    return dream_id

def save_seed(content, db_path=None):
    conn = get_db(db_path) # Pass db_path to get_db
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

def get_dream(dream_id, db_path=None):
    conn = get_db(db_path)
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("SELECT id, content, created_at, length, source, seed_id, is_read FROM dreams WHERE id = %s", (dream_id,))
    else:
        c.execute("SELECT id, content, created_at, length, source, seed_id, is_read FROM dreams WHERE id = ?", (dream_id,))
    row = c.fetchone()
    conn.close()
    if row:
        is_read_value = False
        if DB_TYPE == "postgres":
            is_read_value = row['is_read']
        elif len(row) > 6: # For SQLite, check if column exists by row length
            is_read_value = row[6]
        return {"id": row[0], "content": row[1], "created_at": row[2], "length": row[3],
                "source": row[4], "seed_id": row[5], "is_read": is_read_value}
    return None

def get_all_dreams(limit=20, offset=0, include_read=True):
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        if include_read:
            c.execute("SELECT id, content, created_at, length, source, seed_id, is_read FROM dreams ORDER BY id DESC LIMIT %s OFFSET %s", (limit, offset))
        else:
            c.execute("SELECT id, content, created_at, length, source, seed_id, is_read FROM dreams WHERE is_read = FALSE ORDER BY id DESC LIMIT %s OFFSET %s", (limit, offset))
    else:
        if include_read:
            c.execute("SELECT id, content, created_at, length, source, seed_id, is_read FROM dreams ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
        else:
            c.execute("SELECT id, content, created_at, length, source, seed_id, is_read FROM dreams WHERE is_read = 0 ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "content": r[1], "created_at": r[2], "length": r[3],
            "source": r[4], "seed_id": r[5], "is_read": (r['is_read'] if DB_TYPE == "postgres" else (r[6] if len(r) > 6 else False))} for r in rows]

def get_unread_dreams(limit=20):
    return get_all_dreams(limit=limit, offset=0, include_read=False)

def mark_as_read(dream_id):
    conn = get_db()
    c = conn.cursor()
    if DB_TYPE == "postgres":
        c.execute("UPDATE dreams SET is_read = TRUE WHERE id = %s", (dream_id,))
    else:
        c.execute("UPDATE dreams SET is_read = 1 WHERE id = ?", (dream_id,))
    conn.commit()
    conn.close()
    return True

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

def serialize_dream_data(dream_data):
    if isinstance(dream_data, list):
        return [serialize_dream_data(d) for d in dream_data]
    if isinstance(dream_data, dict):
        if 'created_at' in dream_data and isinstance(dream_data['created_at'], datetime):
            dream_data['created_at'] = dream_data['created_at'].isoformat()
    return dream_data

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
            
            created_at_str = str(item['created_at'])
            pub_date = created_at_str # Default fallback

            try:
                dt_obj = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                pub_date = formatdate(timeval=dt_obj.timestamp(), localtime=False, usegmt=True)
            except ValueError:
                pass
            
            ET.SubElement(item_elem, "pubDate").text = pub_date
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
        try:
            seed_id = int(seed_id)
        except ValueError:
            print(f"Invalid seed_id received: {seed_id}", file=sys.stderr)
            seed_id = None # Treat as if no seed_id was provided

    if seed_id is not None:
        try:
            conn = get_db()
            if conn:
                c = conn.cursor()
                if DB_TYPE == "postgres":
                    c.execute("SELECT content FROM seeds WHERE id = %s", (seed_id,))
                else:
                    c.execute("SELECT content FROM seeds WHERE id = ?", (seed_id,))
                row = c.fetchone()
                conn.close()
                if row:
                    seed_content = row['content']
        except Exception as e:
            print(f"Database error in random_dream: {e}", file=sys.stderr)
            seed_content = None
    content = generate_dream(seed_content)
    if not content:
        return jsonify({"error": "夢の生成に失敗しました"}), 500
    source = 'seed' if seed_content else 'ai'
    try:
        dream_id = save_dream(content, source=source, seed_id=seed_id if seed_content else None)
        dream = get_dream(dream_id)
        fmt = request.args.get('format', 'json')
        if fmt == 'json':
            dream = serialize_dream_data(dream)
        return format_response(dream, fmt)
    except Exception as e:
        print(f"Error saving/retrieving dream: {e}", file=sys.stderr)
        return jsonify({"error": "データベースエラーが発生しました"}), 500

@app.route('/api/dreams')
def list_dreams():
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    dreams = get_all_dreams(limit=limit, offset=offset)
    fmt = request.args.get('format', 'json')
    if fmt == 'json':
        dreams = serialize_dream_data(dreams)
    return format_response(dreams, fmt)

@app.route('/api/dream/<int:dream_id>')
def get_dream_api(dream_id):
    dream = get_dream(dream_id)
    if not dream:
        return jsonify({"error": "夢が見つかりません"}), 404
    fmt = request.args.get('format', 'json')
    if fmt == 'json':
        dream = serialize_dream_data(dream)
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

@app.route('/voice_dream')
def voice_dream_page():
    return render_template('voice_dream.html')

@app.route('/api/dream/last5')
def get_last5_dreams():
    """
    最新 5 件（または過去の指定範囲）を取得します。
    デフォルトは created_at の降順で 5 件。
    """
    limit = 5
    dreams = get_all_dreams(limit=limit, offset=0)   # 既存の get_all_dreams を流用
    # API の format パラメータもそのまま利用できるように
    fmt = request.args.get('format', 'json')
    if fmt == 'json':
        dreams = serialize_dream_data(dreams)
    return format_response(dreams, fmt)

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
        # 初期データのロード（Neonが空の場合）
        load_initial_data()
        print(f"Starting Flask server on port {args.port}...")
        app.run(host='0.0.0.0', port=args.port, debug=True)
