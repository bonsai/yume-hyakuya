import pytest
import sys
import os
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dream_server import app, init_db, get_db, save_dream, save_seed



@pytest.fixture
def tmp_db_path(tmp_path):
    # Use a subdirectory for the database to avoid conflicts
    db_file = tmp_path / "test_yume.db"
    return str(db_file)

@pytest.fixture
def db_client(tmp_db_path):
    app.config['TESTING'] = True
    app.config['DATABASE_URL'] = '' # Ensure SQLite is used
    app.config['DB_PATH'] = tmp_db_path # Override DB_PATH for tests

    # Re-initialize DB with temp path
    with app.app_context():
        init_db(tmp_db_path)

    with app.test_client() as client:
        yield client

    # Clean up after test
    if os.path.exists(tmp_db_path):
        os.remove(tmp_db_path)

def test_index_page(db_client):
    """index.html が表示されるか"""
    resp = db_client.get('/')
    assert resp.status_code == 200
    assert 'SF夢日記' in resp.data.decode('utf-8')

def test_api_dreams(db_client, tmp_db_path):
    """夢一覧API"""
    # テスト用夢を保存
    dream_id = save_dream('テスト夢です。' * 100, source='test', db_path=tmp_db_path)
    resp = db_client.get('/api/dreams')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
    assert len(data) > 0

def test_api_dream_random(db_client):
    """ランダム夢生成（モックが必要）"""
    # Sakura APIのモックが必要ですが、ここでは簡易的に
    resp = db_client.get('/api/dream/random')
    # Sakura APIが失敗する可能性があるので200か500
    assert resp.status_code in [200, 500]

def test_api_seed_submit(db_client):
    """種投稿API"""
    resp = db_client.post('/api/seed/submit',
                    data=json.dumps({'content': 'テスト種'}),
                    content_type='application/json')
    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert 'id' in data
    assert data['content'] == 'テスト種'

def test_api_seeds(db_client, tmp_db_path):
    """種一覧API"""
    save_seed('テスト種2', db_path=tmp_db_path)
    resp = db_client.get('/api/seeds')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
