#!/bin/bash

# 服务器状态检查脚本

echo "=== 检查服务器状态 ==="

# 检查项目目录
echo "1. 检查项目目录..."
if [ -d "/opt/blockscout" ]; then
    echo "✅ 项目目录存在: /opt/blockscout"
    ls -la /opt/blockscout/
else
    echo "❌ 项目目录不存在: /opt/blockscout"
fi

echo ""

# 检查Docker服务
echo "2. 检查Docker服务..."
if command -v docker &> /dev/null; then
    echo "✅ Docker已安装"
    docker --version
else
    echo "❌ Docker未安装"
fi

echo ""

# 检查Docker Compose
echo "3. 检查Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose已安装"
    docker-compose --version
else
    echo "❌ Docker Compose未安装"
fi

echo ""

# 检查端口占用
echo "4. 检查端口占用..."
netstat -tlnp | grep -E ":(4000|4001|4002|7432|7433) " || echo "没有找到相关端口"

echo ""

# 检查Docker容器
echo "5. 检查Docker容器..."
if [ -d "/opt/blockscout/docker-compose" ]; then
    cd /opt/blockscout/docker-compose
    docker-compose ps
else
    echo "❌ docker-compose目录不存在"
fi

echo ""

# 检查防火墙
echo "6. 检查防火墙状态..."
ufw status

echo ""
echo "=== 检查完成 ===" 