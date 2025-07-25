#!/bin/bash

# 服务器端口检查脚本
# 用于部署前检查端口冲突

echo "=== 检查服务器端口占用情况 ==="

# 检查常用端口
PORTS_TO_CHECK=(80 443 22 21 25 110 143 993 995 3306 5432 6379 8080 8081 4000 4001 4002 7432 7433)

echo "检查以下端口：${PORTS_TO_CHECK[*]}"
echo ""

for port in "${PORTS_TO_CHECK[@]}"; do
    if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        echo "❌ 端口 $port 已被占用:"
        netstat -tlnp 2>/dev/null | grep ":$port " | head -1
    else
        echo "✅ 端口 $port 可用"
    fi
done

echo ""
echo "=== Blockscout 将使用的端口 ==="
echo "主服务: 4000 (原80端口)"
echo "统计服务: 4001 (原8080端口)"
echo "可视化服务: 4002 (原8081端口)"
echo "数据库: 7432 (PostgreSQL)"
echo "统计数据库: 7433 (PostgreSQL)"

echo ""
echo "=== 建议的防火墙配置 ==="
echo "ufw allow 4000  # Blockscout主服务"
echo "ufw allow 4001  # 统计服务"
echo "ufw allow 4002  # 可视化服务"
echo "ufw allow 7432  # 数据库(如需要外部访问)"
echo "ufw allow 7433  # 统计数据库(如需要外部访问)" 