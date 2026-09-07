#!/usr/bin/env bash

mkdir -p ./out/code

echo "=== [1/2] Syncing derived class ==="
python3 interface_sync.py \
    --old test/include/IObserver_old.h \
    --new test/include/IObserver.h \
    --src test/src || echo "⚠️ interface_sync.py 脚本执行失败，继续进行编译测试..."

echo "=== [2/2] Checking C++ Compilation ==="

# 定义需要校验的文件与对应的 include 路径
files_to_check=(
    "test/src/LoggerObserver.cpp|-I test/include -I test/src"
    "test/src/NetworkObserver.cpp|-I test/include -I test/src"
    "test/src/strategy/StrategyObserver.cpp|-I test/include -I test/src/strategy"
    "test/src/market/MarketObserver.cpp|-I test/include -I test/src/market"
    "test/src/strategy/alpha/AlphaObserver.cpp|-I test/include -I test/src/strategy/alpha"
    "test/src/strategy/UnrelatedClass.cpp|-I test/include -I test/src/strategy"
    "test/src/market/MarketDataManager.cpp|-I test/include -I test/src/market"
)

failed_count=0

for item in "${files_to_check[@]}"; do
    IFS="|" read -r file flags <<< "$item"
    
    # -fsyntax-only 只做语法检查，不生成 .o 垃圾文件；如果想保留 .o 可以改回 -c
    if g++ -std=c++17 $flags -fsyntax-only "$file" 2>/tmp/compile_err.log; then
        echo "✅ [PASS] $file"
    else
        echo "❌ [FAIL] $file"
        echo "----------------------------------------"
        cat /tmp/compile_err.log
        echo "----------------------------------------"
        ((failed_count++))
    fi
done

echo "========================================"
if [ $failed_count -eq 0 ]; then
    echo "🎉 所有文件均编译检查通过！"
else
    echo "🚨 共有 $failed_count 个文件编译失败，请检查上方日志。"
fi