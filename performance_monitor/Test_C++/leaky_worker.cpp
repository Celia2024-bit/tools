/**
 * leaky_worker.cpp
 * ----------------
 * A deliberately broken worker process with three classic leaks:
 *
 *  LEAK 1 — Memory leak
 *    malloc() called every cycle, never freed.
 *    → monitor: memory_mb climbs steadily
 *
 *  LEAK 2 — Thread leak  (the exact pattern from your IEC 61850 bug)
 *    A new thread is spawned every cycle and never joined/detached.
 *    → monitor: threads + handles climb steadily
 *    → ctx_invol spikes as hundreds of threads compete for CPU
 *
 *  LEAK 3 — Handle / FD leak
 *    A file is opened every cycle but never closed.
 *    → monitor: handles climbs steadily
 *
 * Runs for ~120 seconds.
 * Expected result: check_regression.py EXIT 1 (all metrics breach)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
  #include <windows.h>
  #include <process.h>
  #define SLEEP_MS(ms) Sleep(ms)
  #define TID HANDLE
#else
  #include <pthread.h>
  #include <unistd.h>
  #define SLEEP_MS(ms) usleep((ms)*1000)
  #define TID pthread_t
#endif

#define RUN_SECONDS  120
#define MEM_LEAK_KB  32     /* leaked per cycle */
#define CYCLE_MS     20     /* 50 cycles/sec  ≈ your 50Hz IEC 61850 loop */

/* ── LEAK 2: leaked thread — spins briefly then exits, but is never joined ── */
#ifdef _WIN32
unsigned __stdcall leaked_thread(void* arg)
{
    /* Do a tiny bit of work so threads compete for CPU */
    volatile long sum = 0;
    for (int i = 0; i < 100000; i++) sum += i;
    return 0;
    /* handle is never CloseHandle()'d → handle leak on Windows */
}
#else
void* leaked_thread(void* arg)
{
    volatile long sum = 0;
    for (int i = 0; i < 100000; i++) sum += i;
    return NULL;
    /* never pthread_join()'d or pthread_detach()'d → zombie thread */
}
#endif

/* ── main ────────────────────────────────────────────────────────────────── */
int main(void)
{
    printf("[leaky] starting leak simulation, running for %ds\n", RUN_SECONDS);
    printf("[leaky] LEAK 1: memory  (+%d KB/cycle)\n", MEM_LEAK_KB);
    printf("[leaky] LEAK 2: threads (new thread every %dms, never joined)\n", CYCLE_MS);
    printf("[leaky] LEAK 3: handles (file opened every cycle, never closed)\n");
    fflush(stdout);

    int total_cycles = (RUN_SECONDS * 1000) / CYCLE_MS;

    for (int cycle = 0; cycle < total_cycles; cycle++) {

        /* ── LEAK 1: memory ───────────────────────────────────────────────── */
        char* leak = (char*)malloc(MEM_LEAK_KB * 1024);
        if (leak) {
            memset(leak, cycle & 0xFF, MEM_LEAK_KB * 1024);
            /* intentionally NOT freed */
        }

        /* ── LEAK 2: thread ───────────────────────────────────────────────── */
#ifdef _WIN32
        HANDLE h = (HANDLE)_beginthreadex(NULL, 0, leaked_thread, NULL, 0, NULL);
        /* intentionally NOT CloseHandle(h) */
        (void)h;
#else
        pthread_t t;
        pthread_create(&t, NULL, leaked_thread, NULL);
        /* intentionally NOT pthread_join() or pthread_detach() */
#endif

        /* ── LEAK 3: file handle ──────────────────────────────────────────── */
#ifdef _WIN32
        char path[64];
        snprintf(path, sizeof(path), "tmp_leak_%d.tmp", cycle % 100);
        FILE* f = fopen(path, "w");
        /* intentionally NOT fclose(f) */
        (void)f;
#else
        FILE* f = fopen("/tmp/leak_test.tmp", "w");
        /* intentionally NOT fclose(f) */
        (void)f;
#endif

        /* Print progress every 5 seconds */
        if (cycle % (5000 / CYCLE_MS) == 0) {
            int elapsed = (cycle * CYCLE_MS) / 1000;
            printf("[leaky] t=%ds  cycle=%d  mem_leaked≈%d KB\n",
                   elapsed, cycle, cycle * MEM_LEAK_KB);
            fflush(stdout);
        }

        SLEEP_MS(CYCLE_MS);
    }

    printf("[leaky] done.\n");
    return 0;
}
