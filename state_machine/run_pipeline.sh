#!/usr/bin/env bash
set -e  

mkdir -p ./out/code

echo "🔄 [1/5] Converting Markdown to JSON..."
python3 table_to_json.py ./test/state_machine.md 

echo "📊 [2/5] Generating Mermaid diagram..."
python3 json_to_mermaid.py ./out/state_machine.json

echo "⚙️ [3/5] Generating C++ code..."
python3 json_to_cpp.py ./out/state_machine.json -p Order

echo "🚚 [4/5] Copying test main file..."
cp ./test/main.cpp ./out/code/

echo "🔨 [5/5] Compiling and Running C++ test..."
cd ./out/code
g++ -std=c++17 main.cpp OrderStateMachine.cpp OrderHandler.cpp -o test_sm
./test_sm

echo "✨ All operations completed successfully!"