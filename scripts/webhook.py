#!/usr/bin/env python3
"""
GitHub Webhook 接收器
用于接收 GitHub 推送事件并触发部署
"""

import os
import sys
import json
import hmac
import hashlib
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

# 配置
SECRET_TOKEN = os.getenv('WEBHOOK_SECRET', 'your-secret-token')
DEPLOY_SCRIPT = '/opt/blockscout/scripts/deploy.sh'

def verify_signature(payload_body, signature):
    """验证 GitHub Webhook 签名"""
    if not signature:
        return False
    
    expected_signature = 'sha256=' + hmac.new(
        SECRET_TOKEN.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

@app.route('/webhook', methods=['POST'])
def webhook():
    """处理 GitHub Webhook 请求"""
    # 获取请求数据
    payload_body = request.get_data()
    signature = request.headers.get('X-Hub-Signature-256')
    
    # 验证签名
    if not verify_signature(payload_body, signature):
        return jsonify({'error': 'Invalid signature'}), 401
    
    # 解析事件
    event = request.headers.get('X-GitHub-Event')
    payload = json.loads(payload_body)
    
    # 只处理 push 事件到 main 分支
    if event == 'push' and payload.get('ref') == 'refs/heads/main':
        try:
            # 执行部署脚本
            result = subprocess.run(
                [DEPLOY_SCRIPT],
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                return jsonify({
                    'status': 'success',
                    'message': 'Deployment triggered successfully',
                    'output': result.stdout
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Deployment failed',
                    'error': result.stderr
                }), 500
                
        except subprocess.TimeoutExpired:
            return jsonify({
                'status': 'error',
                'message': 'Deployment timeout'
            }), 500
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    return jsonify({'status': 'ignored', 'message': 'Event ignored'})

@app.route('/health', methods=['GET'])
def health():
    """健康检查端点"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False) 