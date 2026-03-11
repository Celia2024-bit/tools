let socket;
let rtChart = null, trChart = null;
let rtData = { times: [], mem: [], hnd: [], ctx_vol: [], ctx_invol: [], thr: [] };
let trData = { times: [], mem: [], hnd: [], ctx_vol: [], ctx_invol: [], thr: [] };

const isLocal = false;
//const renderHost = "tradesystem-v86g.onrender.com"; 
const renderHost = "performancemonitor-912333184212.europe-west1.run.app"; 
const API_BASE = isLocal ? "http://localhost:8080" : `https://${renderHost}`;
const WS_BASE  = isLocal ? "ws://localhost:8080"  : `wss://${renderHost}`;

window.onload = async () => {
    await refreshProcessList(); 

    const input = document.getElementById('exe-name');
    if (input) {
        input.onfocus = refreshProcessList;
    }
};

// ── Chart creation ───────────────────────────────────────────────────────────
function createCharts() {
    if (rtChart) { rtChart.dispose(); rtChart = null; }
    if (trChart) { trChart.dispose(); trChart = null; }

    const getOption = (title) => ({
        title: { text: title, textStyle: { color: '#eee' } },
        tooltip: { trigger: 'axis' },
        legend: {
            data: ['Memory(MB)', 'Handles', 'Ctx Vol/s', 'Ctx Invol/s', 'Threads'],
            bottom: 0,
            textStyle: { color: '#ccc' }
        },
        grid: { left: '5%', right: '8%', bottom: '15%', containLabel: true },
        xAxis: { type: 'category', data: [], boundaryGap: false },
        yAxis: [
            { type: 'value', name: 'Mem/Ctx', scale: true },
            { type: 'value', name: 'Handles', scale: true, position: 'right' }
        ],
        series: [
            {
                name: 'Memory(MB)',
                type: 'line', showSymbol: false, smooth: true,
                data: [],
                lineStyle: { color: '#4f9cf9' },
                itemStyle: { color: '#4f9cf9' }
            },
            {
                name: 'Handles',
                type: 'line', showSymbol: false, smooth: true,
                yAxisIndex: 1,
                data: [],
                lineStyle: { color: '#f9a84f' },
                itemStyle: { color: '#f9a84f' }
            },
            {
                name: 'Ctx Vol/s',
                type: 'line', showSymbol: false, smooth: true,
                data: [],
                lineStyle: { color: '#4fc98f', type: 'dashed' },
                itemStyle: { color: '#4fc98f' }
            },
            {
                name: 'Ctx Invol/s',
                type: 'line', showSymbol: false, smooth: true,
                data: [],
                lineStyle: { color: '#f94f4f' },
                itemStyle: { color: '#f94f4f' }
            },
            {
                name: 'Threads',
                type: 'line', showSymbol: false, smooth: true,
                data: [],
                lineStyle: { color: '#c792ea' },
                itemStyle: { color: '#c792ea' }
            }
        ]
    });

    rtChart = echarts.init(document.getElementById('realtime-chart'), 'dark');
    rtChart.setOption(getOption('REAL-TIME MONITOR'));

    trChart = echarts.init(document.getElementById('trend-chart'), 'dark');
    trChart.setOption(getOption('LONG-TERM TREND'));
}

// ── WebSocket ────────────────────────────────────────────────────────────────
function connect() {
    console.log(`Connecting to WebSocket: ${WS_BASE}/ws`);
    socket = new WebSocket(`${WS_BASE}/ws`);
    
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        
        if (msg.type === "realtime" && rtChart) {
            updateRT(msg.data);
        } else if ((msg.type === "trend_push" || msg.type === "history_trend") && trChart) {
            updateTR(msg.data);
        } else if (msg.type === "status_log") {
            const el = document.getElementById('status-indicator');
            el.innerText = msg.message;
            if (msg.message.includes("BUILD") || msg.message.includes("FAILED")) {
                const btn = document.getElementById('btn-trade-update');
                btn.innerText = "UPDATE & BUILD";
                btn.disabled = false;
                btn.style.opacity = "1";
            }
            el.className = msg.message.includes("started") ? "status-on" : "";
        }
    };
}

// ── Real-time update ─────────────────────────────────────────────────────────
function updateRT(data) {
    const windowMin = parseFloat(document.getElementById('window-min').value) || 2;
    const interval  = parseFloat(document.getElementById('interval').value)   || 1;
    const maxPoints = Math.floor((windowMin * 60) / interval);

    rtData.times.push(data.timestamp.split(' ')[1]);
    rtData.mem.push(Number(data.memory_mb)       || 0);
    rtData.hnd.push(Number(data.handles)         || 0);
    rtData.ctx_vol.push(Number(data.ctx_vol_per_sec)   || 0);
    rtData.ctx_invol.push(Number(data.ctx_invol_per_sec) || 0);
    rtData.thr.push(Number(data.threads) || 0);

    if (rtData.times.length > maxPoints) {
        rtData.times.shift();
        rtData.mem.shift();
        rtData.hnd.shift();
        rtData.ctx_vol.shift();
        rtData.ctx_invol.shift();
        rtData.thr.shift();
    }

    rtChart.setOption({
        xAxis: { data: rtData.times },
        series: [
            { data: rtData.mem },
            { data: rtData.hnd },
            { data: rtData.ctx_vol },
            { data: rtData.ctx_invol },
            { data: rtData.thr }
        ]
    }, false);
}

// ── Trend update ─────────────────────────────────────────────────────────────
function updateTR(data) {
    if (!trChart) return;
    
    const list = Array.isArray(data) ? data : [data];
    console.log("Trend Data Received:", list[0]);

    list.forEach(i => {
        if (i.timestamp) {
            trData.times.push(i.timestamp.split(' ')[1]);
            trData.mem.push(Number(i.avg_memory)    || 0);
            trData.hnd.push(Number(i.avg_handles)   || 0);
            trData.ctx_vol.push(Number(i.avg_ctx_vol)   || 0);
            trData.ctx_invol.push(Number(i.avg_ctx_invol) || 0);
            trData.thr.push(Number(i.avg_threads) || 0);
        }
    });

    trChart.setOption({
        xAxis: { data: trData.times },
        series: [
            { name: 'Memory(MB)',  data: trData.mem },
            { name: 'Handles',     data: trData.hnd },
            { name: 'Ctx Vol/s',   data: trData.ctx_vol },
            { name: 'Ctx Invol/s', data: trData.ctx_invol },
            { name: 'Threads',     data: trData.thr }
        ]
    });
}

// ── Process list ─────────────────────────────────────────────────────────────
async function refreshProcessList() {
    try {
        const response = await fetch(`${API_BASE}/processes`);
        if (!response.ok) throw new Error('Network response was not ok');
        
        const data = await response.json();
        const listContainer = document.getElementById('process-list');
        
        if (listContainer && data.processes) {
            listContainer.innerHTML = '';
            data.processes.forEach(proc => {
                const option = document.createElement('option');
                option.value = proc;
                listContainer.appendChild(option);
            });
            console.log("Process list updated.");
        }
    } catch (err) {
        console.error("Failed to fetch processes:", err);
    }
}

// ── Button handlers ───────────────────────────────────────────────────────────
document.getElementById('btn-config').onclick = () => {
    const exeName = document.getElementById('exe-name').value;
    
    if (!exeName) {
        alert("Please choose process name!");
        return;
    }

    socket.send(JSON.stringify({
        type: "configure",
        data: {
            exe: exeName,
            interval: parseInt(document.getElementById('interval').value),
            limit: parseInt(document.getElementById('trend-limit').value)
        }
    }));

    const startBtn = document.getElementById('btn-start');
    startBtn.disabled = false;
    startBtn.title = "Ready to start";
    
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
    rtData = { times: [], mem: [], hnd: [], ctx_vol: [], ctx_invol: [], thr: [] };
    trData = { times: [], mem: [], hnd: [], ctx_vol: [], ctx_invol: [], thr: [] };
    createCharts(); 
    socket.send(JSON.stringify({ type: "start" }));
};

document.getElementById('btn-stop').onclick = () => {
    socket.send(JSON.stringify({ type: "stop" }));
    document.getElementById('btn-start').disabled = true;
    if (rtChart) { rtChart.dispose(); rtChart = null; }
    if (trChart) { trChart.dispose(); trChart = null; }
};

document.getElementById('btn-refresh').onclick = async () => {
    const btn = document.getElementById('btn-refresh');
    btn.innerText = "⏳";
    await refreshProcessList();
    btn.innerText = "🔄";
};

document.getElementById('btn-trade-update').onclick = () => {
    const btn = document.getElementById('btn-trade-update');
    btn.innerText = "BUILDING...";
    btn.disabled = true;
    btn.style.opacity = "0.5";
    socket.send(JSON.stringify({ type: "trade_update" }));
    console.log("Update instruction sent...");
};

document.getElementById('btn-trade-start').onclick = () => {
    console.log("Sending: trade_start");
    socket.send(JSON.stringify({ type: "trade_start" }));
};

document.getElementById('btn-trade-stop').onclick = () => {
    console.log("Sending: trade_stop");
    socket.send(JSON.stringify({ type: "trade_stop" }));
};

connect();