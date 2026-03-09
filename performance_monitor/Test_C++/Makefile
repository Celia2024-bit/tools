# Makefile
# Builds healthy_worker and leaky_worker with gcc
# Works on Windows (MinGW) and Linux
#
# Usage:
#   make all          — build both
#   make healthy      — build healthy only
#   make leaky        — build leaky only
#   make clean        — remove binaries and temp files

CXX     = g++
CFLAGS  = -O2 -Wall

# Detect OS
ifeq ($(OS), Windows_NT)
    EXT      = .exe
    LDFLAGS  = -lws2_32
    RM       = del /Q
    CLEAN_TMP = del /Q *.tmp 2>nul || true
else
    EXT      =
    LDFLAGS  = -lpthread
    RM       = rm -f
    CLEAN_TMP = rm -f *.tmp /tmp/leak_test.tmp
endif

HEALTHY = healthy_worker$(EXT)
LEAKY   = leaky_worker$(EXT)

.PHONY: all healthy leaky clean

all: healthy leaky
	@echo ""
	@echo "Built:"
	@echo "  $(HEALTHY)  — clean worker, monitor should show flat metrics"
	@echo "  $(LEAKY)    — leaky worker, monitor should show upward trends"
	@echo ""
	@echo "Run monitor against one of them, then check results:"
	@echo "  python3 run_monitor.py --exe $(HEALTHY) --interval 2 --limit 5"
	@echo "  python3 check_regression.py --trend_csv trend_performance.csv"

healthy: healthy_worker.cpp
	$(CXX) $(CFLAGS) -o $(HEALTHY) healthy_worker.cpp $(LDFLAGS)
	@echo "✅ built $(HEALTHY)"

leaky: leaky_worker.cpp
	$(CXX) $(CFLAGS) -o $(LEAKY) leaky_worker.cpp $(LDFLAGS)
	@echo "✅ built $(LEAKY)"

clean:
	$(RM) $(HEALTHY) $(LEAKY) 2>/dev/null || true
	$(CLEAN_TMP)
	$(RM) *.csv 2>/dev/null || true
	@echo "✅ cleaned"
