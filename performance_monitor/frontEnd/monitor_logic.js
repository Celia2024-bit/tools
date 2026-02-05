let socket;
let rtChart = null, trChart = null;
let rtData = { times: [], mem: [], hnd: [] };
let trData = { times: [], mem: [], hnd: [] };

const isLocal = false;
// 你的 Render 后端地址 (去掉 https:// 前缀)
const renderHost = "tradesystem-v86g.onrender.com"; 

const API_BASE = isLocal ? "http://localhost:8080" : `https://${renderHost}`;
const WS_BASE  = isLocal ? "ws://localhost:8080"  : `wss://${renderHost}`;

window.onload = async () => {
    // 1. 立即获取进程列表
    await refreshProcessList(); 

    // 4. 小优化：当用户点击输入框时，自动刷新一次列表，确保能选到刚打开的程序
    const input = document.getElementById('exe-name');
    if (input) {
        input.onfocus = refreshProcessList;
    }
};

// 1. 彻底的图表创建函数
function createCharts() {
    // 如果已经存在，先销毁，防止 coordinateSystem 冲突
    if (rtChart) { rtChart.dispose(); rtChart = null; }
    if (trChart) { trChart.dispose(); trChart = null; }

    const getOption = (title) => ({
        title: { text: title, textStyle: { color: '#eee' } },
        tooltip: { trigger: 'axis' },
        legend: { data: ['Memory(MB)', 'Handles'], bottom: 0 },
        grid: { left: '5%', right: '5%', bottom: '15%', containLabel: true },
        xAxis: { type: 'category', data: [], boundaryGap: false },
        yAxis: [
            { type: 'value', name: 'Memory', scale: true },
            { type: 'value', name: 'Handles', scale: true, position: 'right' }
        ],
        series: [
            { name: 'Memory(MB)', type: 'line', showSymbol: false, smooth: true, data: [] },
            { name: 'Handles', type: 'line', showSymbol: false, smooth: true, yAxisIndex: 1, data: [] }
        ]
    });

    rtChart = echarts.init(document.getElementById('realtime-chart'), 'dark');
    rtChart.setOption(getOption('REAL-TIME MONITOR'));

    trChart = echarts.init(document.getElementById('trend-chart'), 'dark');
    trChart.setOption(getOption('LONG-TERM TREND'));
}

// 2. 连接逻辑
function connect() {
    console.log(`Connecting to WebSocket: ${WS_BASE}/ws`);
    socket = new WebSocket(`${WS_BASE}/ws`);
    
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        
        // 核心防御：只有图表对象存在时才尝试更新
        if (msg.type === "realtime" && rtChart) {
            updateRT(msg.data);
        } else if ((msg.type === "trend_push" || msg.type === "history_trend") && trChart) {
            updateTR(msg.data);
        } else if (msg.type === "status_log") {
            const el = document.getElementById('status-indicator');
            el.innerText = msg.message;
            if (msg.message.includes("BUILD") || msg.message.includes("FAILED")) {
                const btn = document.getElementById('btn-trade-update');
                btn.innerText = "UPDATE & BUILD"; // 恢复文字
                btn.disabled = false;            // 启用按钮
                btn.style.opacity = "1";         // 恢复亮度
            }
            el.className = msg.message.includes("started") ? "status-on" : "";
        }
    };
}

function updateRT(data) {
    const windowMin = parseFloat(document.getElementById('window-min').value) || 2;
    const interval = parseFloat(document.getElementById('interval').value) || 1;
    const maxPoints = Math.floor((windowMin * 60) / interval);

    rtData.times.push(data.timestamp.split(' ')[1]);
    rtData.mem.push(data.memory_mb);
    rtData.hnd.push(data.handles);

    if (rtData.times.length > maxPoints) {
        rtData.times.shift(); rtData.mem.shift(); rtData.hnd.shift();
    }

    // 使用 notMerge: true 确保坐标系强制重绘
    rtChart.setOption({
        xAxis: { data: rtData.times },
        series: [{ data: rtData.mem }, { data: rtData.hnd }]
    }, false); 
}

function updateTR(data) {
    if (!trChart) return;
    
    const list = Array.isArray(data) ? data : [data];
    console.log("Trend Data Received:", list[0]); // 在 F12 控制台看一眼这个对象里的字段对不对

    list.forEach(i => {
        if (i.timestamp) {
            trData.times.push(i.timestamp.split(' ')[1]);
            
            // 重要：根据你的 constants.py，确保 key 名字完全一致
            // 并且强制转为 Number，防止字符串导致 ECharts 报错
            trData.mem.push(Number(i.avg_memory) || 0); 
            trData.hnd.push(Number(i.avg_handles) || 0);
        }
    });

    trChart.setOption({
        xAxis: { data: trData.times },
        series: [
            { name: 'Memory(MB)', data: trData.mem },
            { name: 'Handles', data: trData.hnd }
        ]
    });
}

async function refreshProcessList() {
    try {
        const response = await fetch(`${API_BASE}/processes`);
        if (!response.ok) throw new Error('Network response was not ok');
        
        const data = await response.json();
        const listContainer = document.getElementById('process-list');
        
        if (listContainer && data.processes) {
            listContainer.innerHTML = ''; // 先清空旧的列表
            data.processes.forEach(proc => {
                const option = document.createElement('option');
                option.value = proc; // 将进程名赋给 option
                listContainer.appendChild(option);
            });
            console.log("Process list updated.");
        }
    } catch (err) {
        console.error("Failed to fetch processes:", err);
    }
}

// 3. 按钮逻辑
document.getElementById('btn-config').onclick = () => {
    const exeName = document.getElementById('exe-name').value;
    
    if (!exeName) {
        alert("Please choose process name ！");
        return;
    }

    // 1. 发送配置到后端
    socket.send(JSON.stringify({
        type: "configure",
        data: {
            exe: exeName,
            interval: parseInt(document.getElementById('interval').value),
            limit: parseInt(document.getElementById('trend-limit').value)
        }
    }));

    // 2. 【关键步骤】配置发送后，激活 START 按钮
    const startBtn = document.getElementById('btn-start');
    startBtn.disabled = false;
    startBtn.title = "Ready to start"; // 修改鼠标悬停提示
    
    // 3. 视觉反馈：让用户知道配置成功了
    const cfgBtn = document.getElementById('btn-config');
    cfgBtn.innerText = "CONFIGURED ✓";
    cfgBtn.style.background = "#28a745";
    
    setTimeout(() => {
        cfgBtn.innerText = "CONFIGURE";
        cfgBtn.style.background = "#007bff";
    }, 1500);

    console.log("Configuration applied. Start button enabled.");
};

document.getElementById('btn-start').onclick = () => {
    // 关键点：点击 Start 时才真正创建/重置图表
    rtData = { times: [], mem: [], hnd: [] };
    trData = { times: [], mem: [], hnd: [] };
    createCharts(); 
    
    socket.send(JSON.stringify({ type: "start" }));
};

document.getElementById('btn-stop').onclick = () => {
    socket.send(JSON.stringify({ type: "stop" }));
    
    // 停止后把 START 重新变灰，确保逻辑严谨
    document.getElementById('btn-start').disabled = true;
    
    if(rtChart) { rtChart.dispose(); rtChart = null; }
    if(trChart) { trChart.dispose(); trChart = null; }
};

document.getElementById('btn-refresh').onclick = async () => {
    const btn = document.getElementById('btn-refresh');
    btn.innerText = "⏳"; // 变成等待图标
    await refreshProcessList(); // 重新请求后端
    btn.innerText = "🔄"; // 恢复
};

// --- 新增：交易系统控制逻辑 ---

// (1) 更新并编译按钮
document.getElementById('btn-trade-update').onclick = () => {
    const btn = document.getElementById('btn-trade-update');
    btn.innerText = "BUILDING..."; // 改变文字
    btn.disabled = true;           // 禁用按钮，防止连点
    btn.style.opacity = "0.5";     // 视觉上变灰

    socket.send(JSON.stringify({ type: "trade_update" }));
    console.log("Update instruction sent...");
};

// (2) 启动系统按钮
document.getElementById('btn-trade-start').onclick = () => {
    console.log("Sending: trade_start");
    socket.send(JSON.stringify({ type: "trade_start" }));
};

// (3) 关闭系统按钮
document.getElementById('btn-trade-stop').onclick = () => {
    console.log("Sending: trade_stop");
    socket.send(JSON.stringify({ type: "trade_stop" }));
};

// 页面加载只连 WebSocket，不画图
connect();