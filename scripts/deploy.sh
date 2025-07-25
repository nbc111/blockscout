#!/bin/bash

# 自动化部署脚本
set -e

# 配置变量
PROJECT_DIR="/opt/blockscout"
DOCKER_COMPOSE_DIR="$PROJECT_DIR/docker-compose"
LOG_FILE="/var/log/blockscout-deploy.log"

# 端口配置
MAIN_PORT=4000
STATS_PORT=4001
VISUALIZER_PORT=4002
DB_PORT=7432
STATS_DB_PORT=7433

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOG_FILE
}

# 开始部署
log "开始部署 Blockscout..."

# 检查端口占用
log "检查端口占用情况..."
$PROJECT_DIR/scripts/check-ports.sh

# 配置防火墙
log "配置防火墙..."
ufw allow $MAIN_PORT 2>/dev/null || true
ufw allow $STATS_PORT 2>/dev/null || true
ufw allow $VISUALIZER_PORT 2>/dev/null || true

# 进入项目目录
cd $PROJECT_DIR

# 拉取最新代码
log "拉取最新代码..."
git fetch origin
git reset --hard origin/main

# 停止现有服务
log "停止现有服务..."
cd $DOCKER_COMPOSE_DIR
docker-compose down

# 拉取最新镜像
log "拉取最新镜像..."
docker-compose pull

# 启动服务
log "启动服务..."
docker-compose up -d

# 清理无用镜像
log "清理无用镜像..."
docker system prune -f

# 检查服务状态
log "检查服务状态..."
sleep 10
docker-compose ps

log "部署完成！" 