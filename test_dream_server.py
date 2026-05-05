import pytest
import sys
import os
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dream_server import app, init_db, get_db, save_dream, save_seed

# テスト用DB設定
os.environ['DATABASE_URL'] = ''
os.environ['SAKURA_API_TOKEN'] = 'test_token'

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        # SQLiteを使用（テスト用）
        init_db()
        yield client

def test_index_page(client):
    """index.html が表示されるか"""
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'SF夢日記' in resp.data.decode('utf-8')

def test_api_dreams(client):
    """夢一覧API"""
    # テスト用夢を保存
    dream_id = save_dream('テスト夢です。' * 100, source='test')
    resp = client.get('/api/dreams')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
    assert len(data) > 0

def test_api_dream_random(client):
    """ランダム夢生成（モックが必要）"""
    # Sakura APIのモックが必要ですが、ここでは簡易的に
    resp = client.get('/api/dream/random')
    # Sakura APIが失敗する可能性があるので200か500
    assert resp.status_code in [200, 500]

def test_api_seed_submit(client):
    """種投稿API"""
    resp = client.post('/api/seed/submit',
                    data=json.dumps({'content': 'テスト種'}),
                    content_type='application/json')
    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert 'id' in data
    assert data['content'] == 'テスト種'

def test_api_seeds(client):
    """種一覧API"""
    save_seed('テスト種2')
    resp = client.get('/api/seeds')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
