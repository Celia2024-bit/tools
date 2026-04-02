# Makefile
# Builds healthy_worker, leaky_worker and pressure with g++

CXX      = g++
# 建议增加 -static 确保 .exe 在 Windows 其他机器上也能跑
CFLAGS   = -O2 -Wall -static

# Detect OS
ifeq ($(OS), Windows_NT)
    EXT       = .exe
    # Windows 需要链接 ws2_32 (网络) 和 winmm (高精度定时器)
    LDFLAGS   = -lws2_32 -lwinmm
    RM        = del /Q
    # Windows 下创建目录的命令
    MKDIR     = if not exist $(subst /,\,$(1)) mkdir $(subst /,\,$(1))
else
    EXT       =
    LDFLAGS   = -lpthread
    RM        = rm -f
    MKDIR     = mkdir -p $(1)
endif

# 目标路径
HEALTHY  = MemoryLeak/healthy_worker$(EXT)
LEAKY    = MemoryLeak/leaky_worker$(EXT)
PRESSURE = ContextSwitches/pressure$(EXT)

.PHONY: all healthy leaky pressure clean dirs

all: dirs healthy leaky pressure
	@echo ""
	@echo "✅ Build Complete:"
	@echo "  1. $(HEALTHY)  - Normal memory/CPU usage"
	@echo "  2. $(LEAKY)    - Simulated memory leak"
	@echo "  3. $(PRESSURE) - High context switch simulation"
	@echo ""
	@echo "Usage Example:"
	@echo "  python run_monitor.py --exe $(PRESSURE) --interval 1 --limit 10"

# 自动创建子目录防止报错
dirs:
	@$(call MKDIR,MemoryLeak)
	@$(call MKDIR,ContextSwitches)

healthy: MemoryLeak/healthy_worker.cpp
	$(CXX) $(CFLAGS) -o $(HEALTHY) MemoryLeak/healthy_worker.cpp $(LDFLAGS)
	@echo "Built $(HEALTHY)"

leaky: MemoryLeak/leaky_worker.cpp
	$(CXX) $(CFLAGS) -o $(LEAKY) MemoryLeak/leaky_worker.cpp $(LDFLAGS)
	@echo "Built $(LEAKY)"
  
pressure: ContextSwitches/pressure.cpp
	$(CXX) $(CFLAGS) -o $(PRESSURE) ContextSwitches/pressure.cpp $(LDFLAGS)
	@echo "Built $(PRESSURE)"

clean:
	$(RM) $(HEALTHY) $(LEAKY) $(PRESSURE) 2>nul || true
	$(RM) *.csv 2>nul || true
	@echo "Cleaned binaries and CSVs"