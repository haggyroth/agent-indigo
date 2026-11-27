"""Build the two-core link-cable binding (cffi) — a PROTOTYPE for #363 (a trade partner for trade evolutions).

    python -m game._mgba_link_build        # compiles game/_mgba_link*.so (separate from the main binding on purpose)

libmgba ships the cable protocol (`GBASIOLockstep`, exported, internal headers installed) but not the host half: a table of callbacks (`mLockstep`: lock / unlock / signal / wait / addCycles /
useCycles / unusedCycles / unload) that lets one core sleep while the other catches up. mGBA's Qt frontend writes them on top of its core threads; here they are ~100 lines of pthread mutex +
condition variables. The lock is the condition variable's mutex, so a core that sleeps inside `wait` / `useCycles` (called with the lock held, from the SIO timing event) releases it.

Both cores run in their own thread (cffi drops the GIL for the call) and are coupled only through those callbacks. `link_run(n)` runs every attached core for n frames and returns when
all are done; a stop flag releases a sleeper whose partner has finished. Core handles are `pycore_load()` handles of the main binding (its first member is the `struct mCore*`).
"""
import os

import cffi

PREFIX = os.environ.get("MGBA_PREFIX", "/opt/homebrew")
INCLUDE = os.path.join(PREFIX, "include")
LIBDIR = os.path.join(PREFIX, "lib")

ffi = cffi.FFI()
ffi.cdef("""
    int      link_create(void);                          /* 0 = ok */
    void     link_destroy(void);
    int      link_attach(void* pycore);                  /* the node id (0 = master), or -1 */
    int      link_run(int frames, int timeout_ms);       /* 0 = ok, 1 = timed out (deadlock: see link_state) */
    int      link_attached(void);
    uint32_t link_frame_counter(int id);
    int      link_mode(int id);                          /* the SIO mode a node's game has selected */
    uint32_t link_cycles_posted(int id);
    void     link_state(int id, int* awake, unsigned* waitMask, int* frames_done, int* done);
""")

ffi.set_source(
    "game._mgba_link",
    r"""
    #include <mgba/core/core.h>
    #include <mgba/core/lockstep.h>
    #include <mgba/core/timing.h>
    #include <mgba/internal/gba/gba.h>
    #include <mgba/internal/gba/sio.h>
    #include <mgba/internal/gba/sio/lockstep.h>
    #include <pthread.h>
    #include <stdlib.h>
    #include <string.h>
    #include <time.h>
    #include <errno.h>

    typedef struct { struct mCore* core; } PyCoreHead;           /* the main binding's PyCore starts with its core */

    typedef struct {
        struct mCore* core;
        struct GBASIOLockstepNode node;
        pthread_cond_t cv;
        int awake;
        unsigned waitMask;
        int32_t cyclesPosted;
        int frames, done, framesDone, waitReq;
        long tick;
        pthread_t thread;
    } Player;

    static struct GBASIOLockstep L;
    static Player P[MAX_GBAS];
    static struct { int awake; unsigned waitMask; int framesDone, done; int32_t cyclesPosted; long tick; } SNAP[MAX_GBAS];
    static int NP = 0;
    static int created = 0;
    static pthread_mutex_t M = PTHREAD_MUTEX_INITIALIZER;
    static volatile int stopping = 0;

    static void ls_lock(struct mLockstep* l)   { (void)l; pthread_mutex_lock(&M); }
    static void ls_unlock(struct mLockstep* l) { (void)l; pthread_mutex_unlock(&M); }

    /* mCoreThreadWaitFromThread is a REQUEST: the core thread honours it between run-loop iterations, i.e. after the event handler that asked has returned (so a master that waits
       still posts its cycles to the slaves on the lines after wait()). Blocking inside the callback deadlocks both cores. */
    static void sleep_player(Player* p) { p->awake = 0; p->waitReq = 1; }
    static void wake_player(Player* p) { p->awake = 1; p->waitReq = 0; pthread_cond_signal(&p->cv); }

    static bool ls_signal(struct mLockstep* l, unsigned mask) {
        (void)l;
        Player* p = &P[0];
        bool woke = false;
        p->waitMask &= ~mask;
        if (!p->waitMask && p->awake < 1) { wake_player(p); woke = true; }
        return woke;
    }
    static bool ls_wait(struct mLockstep* l, unsigned mask) {
        (void)l;
        Player* p = &P[0];
        bool slept = false;
        p->waitMask |= mask;
        if (p->awake > 0) { slept = true; sleep_player(p); }
        return slept;
    }
    static void ls_addCycles(struct mLockstep* l, int id, int32_t cycles) {
        (void)l;
        if (cycles < 0) abort();
        if (!id) {
            for (int i = 1; i < NP; ++i) {
                Player* p = &P[i];
                if (p->node.d.p->mode > SIO_MULTI) continue;
                p->cyclesPosted += cycles;
                if (p->awake < 1) p->node.nextEvent += p->cyclesPosted;
                wake_player(p);
            }
        } else {
            P[id].cyclesPosted += cycles;
        }
    }
    static int32_t ls_useCycles(struct mLockstep* l, int id, int32_t cycles) {
        (void)l;
        Player* p = &P[id];
        p->tick++;
        p->cyclesPosted -= cycles;
        if (p->cyclesPosted <= 0) sleep_player(p);
        return p->cyclesPosted;
    }
    static int32_t ls_unusedCycles(struct mLockstep* l, int id) { (void)l; return P[id].cyclesPosted; }
    static void ls_unload(struct mLockstep* l, int id) {
        if (id) {
            P[id].cyclesPosted = 0;
            Player* m = &P[0];
            m->waitMask &= ~(1u << id);
            if (!m->waitMask && m->awake < 1) wake_player(m);
        } else {
            for (int i = 1; i < NP; ++i) {
                Player* p = &P[i];
                p->cyclesPosted += ((struct GBASIOLockstep*)l)->players[0]->eventDiff;
                if (p->awake < 1) { p->node.nextEvent += p->cyclesPosted; wake_player(p); }
            }
        }
    }

    int link_create(void) {
        if (created) return 1;
        memset(P, 0, sizeof P);
        NP = 0; stopping = 0;
        mLockstepInit(&L.d);
        GBASIOLockstepInit(&L);
        L.d.context = NULL;
        L.d.lock = ls_lock;  L.d.unlock = ls_unlock;
        L.d.signal = ls_signal;  L.d.wait = ls_wait;
        L.d.addCycles = ls_addCycles;  L.d.useCycles = ls_useCycles;  L.d.unusedCycles = ls_unusedCycles;  L.d.unload = ls_unload;
        created = 1;
        return 0;
    }
    void link_destroy(void) {
        for (int i = 0; i < NP; ++i) { GBASIOLockstepDetachNode(&L, &P[i].node); pthread_cond_destroy(&P[i].cv); }
        NP = 0; created = 0;
    }
    int link_attach(void* h) {
        if (!created || NP >= MAX_GBAS || !h) return -1;
        struct mCore* core = ((PyCoreHead*)h)->core;
        Player* p = &P[NP];
        memset(p, 0, sizeof *p);
        p->core = core;
        pthread_cond_init(&p->cv, NULL);
        p->awake = 1;
        GBASIOLockstepNodeCreate(&p->node);
        if (!GBASIOLockstepAttachNode(&L, &p->node)) return -1;
        struct GBA* gba = (struct GBA*) core->board;
        GBASIOSetDriver(&gba->sio, &p->node.d, SIO_MULTI);
        GBASIOSetDriver(&gba->sio, &p->node.d, SIO_NORMAL_32);
        return NP++;
    }
    static void* runner(void* arg) {
        Player* p = (Player*) arg;
        struct mCore* core = p->core;
        uint32_t target = core->frameCounter(core) + p->frames;
        while (!stopping && (int32_t)(target - core->frameCounter(core)) > 0) {
            pthread_mutex_lock(&M);
            while (p->waitReq && !stopping) pthread_cond_wait(&p->cv, &M);
            pthread_mutex_unlock(&M);
            core->runLoop(core);
            p->framesDone = p->frames - (int)(target - core->frameCounter(core));
        }
        pthread_mutex_lock(&M);
        p->done = 1;
        pthread_mutex_unlock(&M);
        return NULL;
    }
    int link_run(int frames, int timeout_ms) {
        stopping = 0;
        for (int i = 0; i < NP; ++i) { P[i].frames = frames; P[i].done = 0; P[i].framesDone = 0; pthread_create(&P[i].thread, NULL, runner, &P[i]); }
        struct timespec t0, t;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        int timed_out = 0;
        for (;;) {
            pthread_mutex_lock(&M);
            int all = 1;
            for (int i = 0; i < NP; ++i) if (!P[i].done) all = 0;
            /* the master finished: a slave still sleeping for cycles would wait forever — release them */
            if (P[0].done) for (int i = 1; i < NP; ++i) if (!P[i].done) { P[i].cyclesPosted = 1 << 30; wake_player(&P[i]); }
            pthread_mutex_unlock(&M);
            if (all) break;
            clock_gettime(CLOCK_MONOTONIC, &t);
            long ms = (t.tv_sec - t0.tv_sec) * 1000 + (t.tv_nsec - t0.tv_nsec) / 1000000;
            if (ms > timeout_ms) { timed_out = 1; break; }
            struct timespec nap = {0, 2000000};
            nanosleep(&nap, NULL);
        }
        if (timed_out) {
            pthread_mutex_lock(&M);
            for (int i = 0; i < NP; ++i) { SNAP[i].awake = P[i].awake; SNAP[i].waitMask = P[i].waitMask; SNAP[i].framesDone = P[i].framesDone; SNAP[i].done = P[i].done; SNAP[i].cyclesPosted = P[i].cyclesPosted; SNAP[i].tick = P[i].tick; }
            stopping = 1;
            for (int i = 0; i < NP; ++i) pthread_cond_broadcast(&P[i].cv);
            pthread_mutex_unlock(&M);
        }
        for (int i = 0; i < NP; ++i) pthread_join(P[i].thread, NULL);
        for (int i = 1; i < NP; ++i) if (P[i].cyclesPosted > (1 << 29)) P[i].cyclesPosted = 0;   /* the release above gave a slave free cycles: the next run starts gated again (a transfer in progress is left as it is) */
        return timed_out;
    }
    int link_attached(void) { return NP; }
    uint32_t link_frame_counter(int id) { return (id >= 0 && id < NP) ? (uint32_t) P[id].core->frameCounter(P[id].core) : 0; }
    int link_mode(int id) { return (id >= 0 && id < NP) ? (int) P[id].node.mode : -1; }
    void link_state(int id, int* awake, unsigned* waitMask, int* frames_done, int* done) {
        *awake = SNAP[id].awake; *waitMask = SNAP[id].waitMask; *frames_done = SNAP[id].framesDone; *done = SNAP[id].done;
    }
    uint32_t link_cycles_posted(int id) { return (id >= 0 && id < NP) ? (uint32_t) P[id].cyclesPosted : 0; }
    """,
    include_dirs=[INCLUDE],
    library_dirs=[LIBDIR],
    libraries=["mgba"],
    extra_link_args=[f"-Wl,-rpath,{LIBDIR}"],
)

if __name__ == "__main__":
    ffi.compile(verbose=True)
    print("built game/_mgba_link")
