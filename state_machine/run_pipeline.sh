#!/usr/bin/env bash
set -e  # 任何一步报错立即停止执行

# 1. 自动创建所需目录
mkdir -p ./out/code

echo "🔄 [1/5] Converting Markdown to JSON..."
python3 table_to_json.py ./test/state_machine.md -o ./out/state_machine.json

echo "📊 [2/5] Generating Mermaid diagram..."
python3 json_to_mermaid.py ./out/state_machine.json -o ./out/state_machine.mmd

echo "⚙️ [3/5] Generating C++ code..."
# 注：如果 table_to_json.py 已经把 prefix 写进了 JSON，这里的 -p Order 可以省略
python3 json_to_cpp.py ./out/state_machine.json -p Order -o ./out/code

echo "🚚 [4/5] Copying test main file..."
cp ./test/main.cpp ./out/code/

echo "🔨 [5/5] Compiling and Running C++ test..."
cd ./out/code
g++ -std=c++17 main.cpp OrderStateMachine.cpp OrderHandler.cpp -o test_sm
./test_sm

echo "✨ All operations completed successfully!"