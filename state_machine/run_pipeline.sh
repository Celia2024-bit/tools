#!/usr/bin/env bash
set -e  

# 1. 获取传入的 md 文件路径（默认 ./test/state_machine.md）
INPUT_MD="${1:-./test/state_machine.md}"

# 2. 从输入文件路径提取不带后缀的文件名 (例如 output/1.md -> 1)
FILENAME=$(basename "${INPUT_MD}" .md)

# 3. 对应 table_to_json.py 默认生成的 JSON 路径
JSON_FILE="./out/${FILENAME}.json"

echo "📄 Using input file: ${INPUT_MD}"
echo "📦 Target JSON file: ${JSON_FILE}"

mkdir -p ./out/code

echo "🔄 [1/4] Converting Markdown to JSON..."
python3 table_to_json.py "${INPUT_MD}"

echo "📊 [2/4] Generating Mermaid diagram..."
python3 json_to_mermaid.py "${JSON_FILE}"

echo "⚙️ [3/4] Generating C++ code..."
python3 json_to_cpp.py "${JSON_FILE}" -p Order

echo "🔨 [4/4] Compiling and Running C++ test..."
cd ./out/code
g++ -std=c++17 main.cpp OrderStateMachine.cpp OrderHandler.cpp -o test_sm
./test_sm

echo "✨ All operations completed successfully!"