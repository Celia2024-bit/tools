/**
 * healthy_worker.cpp
 * ------------------
 * A well-behaved worker process.
 * - Fixed thread pool, threads are reused not recreated
 * - Memory allocated and freed properly
 * - Handles/FDs closed after use
 * - Runs for ~120 seconds then exits cleanly
 *
 * Expected monitor output:
 *   ctx_invol : low and flat
 *   memory    : flat
 *   threads   : flat (pool size constant)
 *   handles   : flat
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

#define POOL_SIZE     8      /* fixed number of worker threads */
#define RUN_SECONDS   120
#define WORK_BUF_KB   4    /* each worker allocates this, then frees it */

/* ── worker thread ───────────────────────────────────────────────────────── */
#ifdef _WIN32
unsigned __stdcall worker(void* arg)
#else
void* worker(void* arg)
#endif
{
    int id = *(int*)arg;
    while (1) {
        /* Allocate a buffer, do some work, free it */
        char* buf = (char*)malloc(WORK_BUF_KB * 1024);
        if (buf) {
            memset(buf, id & 0xFF, WORK_BUF_KB * 1024);
            free(buf);   /* <-- freed correctly */
        }

        /* Open a temp file, write, close */
#ifdef _WIN32
        char path[64];
        snprintf(path, sizeof(path), "tmp_healthy_%d.tmp", id);
        FILE* f = fopen(path, "w");
        if (f) { fprintf(f, "ok\n"); fclose(f); remove(path); }  /* closed */
#else
        FILE* f = tmpfile();
        if (f) { fprintf(f, "ok\n"); fclose(f); }                /* closed */
#endif

        SLEEP_MS(200);   /* yield willingly → voluntary ctx switches */
    }
#ifndef _WIN32
    return NULL;
#endif
}

/* ── main ────────────────────────────────────────────────────────────────── */
int main(void)
{
    printf("[healthy] starting %d-thread pool, running for %ds\n",
           POOL_SIZE, RUN_SECONDS);

    int ids[POOL_SIZE];
    TID tids[POOL_SIZE];

    for (int i = 0; i < POOL_SIZE; i++) {
        ids[i] = i;
#ifdef _WIN32
        tids[i] = (HANDLE)_beginthreadex(NULL, 0, worker, &ids[i], 0, NULL);
#else
        pthread_create(&tids[i], NULL, worker, &ids[i]);
#endif
    }

    /* Run for RUN_SECONDS, print stats every 10s */
    for (int t = 0; t < RUN_SECONDS; t += 10) {
        SLEEP_MS(10000);
        printf("[healthy] t=%ds - pool alive, no leaks\n", t + 10);
        fflush(stdout);
    }

#ifdef _WIN32
    for (int i = 0; i < POOL_SIZE; i++) { CloseHandle(tids[i]); }
#endif
    printf("[healthy] done. exiting cleanly.\n");
    return 0;
}