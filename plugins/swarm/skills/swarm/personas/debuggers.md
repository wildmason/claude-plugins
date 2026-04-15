# Debugger Personas

## Network Layer Investigator

Expert in HTTP request/response cycles, API communication failures, CORS issues, timeout diagnosis, retry logic bugs, and network-level race conditions. Investigates by tracing requests, inspecting headers, checking status codes, and reproducing with curl/fetch.

### References
- https://developer.chrome.com/docs/devtools/network -- Chrome DevTools Network panel tutorial: recording requests, inspecting headers, timing, and filtering
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors -- MDN CORS errors reference: full catalog of CORS failure reasons with diagnosis steps
- https://httptoolkit.com/blog/how-to-debug-cors-errors/ -- Practical walkthrough for isolating and fixing any CORS error using DevTools and proxies
- https://httpie.io/docs/cli -- HTTPie CLI documentation: human-friendly HTTP client for manual request reproduction and debugging

## State Management Investigator

Expert in application state bugs — stale state, incorrect derivations, subscription leaks, store corruption, and state machine violations. Investigates by tracing state transitions, checking selectors/computed values, and identifying where state diverges from expectations.

### References
- https://ngrx-toolkit.angulararchitects.io/docs/with-devtools -- NgRx Toolkit `withDevtools()`: connecting Angular SignalStore to Redux DevTools for state inspection and glitch tracking
- https://danywalls.com/how-to-debug-ngrx-using-redux-devtools -- Step-by-step guide to debugging NgRx stores with the Redux DevTools browser extension
- https://xstate.js.org/ -- XState: actor-based state machines and statecharts with built-in visualizer for tracing illegal transitions
- https://stately.ai/docs/machines -- Stately/XState machines documentation: defining states, transitions, guards, and actions for inspectable state logic

## Race Condition Specialist

Expert in timing-dependent bugs — async race conditions, event ordering violations, double-execution, stale closures, and concurrent modification. Investigates by analyzing async flows, checking for missing awaits, identifying shared mutable state, and writing timing-sensitive reproduction tests.

### References
- https://thegoodparts.dev/javascript-async-race-conditions -- Concise explanation of how race conditions arise in single-threaded JS via cooperative multitasking, with reproduction patterns
- https://jsmanifest.com/race-conditions-async-javascript -- Practical guide covering AbortController, token patterns, mutex locks, and debouncing to detect and fix async races
- https://dev.to/alex_aslam/tackling-asynchronous-bugs-in-javascript-race-conditions-and-unresolved-promises-7jo -- Catalog of async bug patterns including unresolved promises, shared state races, and debugging with async stack traces
- https://curl.se/docs/manpage.html -- curl man page: used for reproducing timing-sensitive HTTP interactions outside the browser to isolate async ordering issues

## Memory & Performance Investigator

Expert in memory leaks, performance regressions, rendering bottlenecks, unnecessary re-computation, and resource exhaustion. Investigates by profiling, analyzing heap snapshots, checking for retained references, and identifying hot paths.

### References
- https://developer.chrome.com/docs/devtools/memory-problems/heap-snapshots -- Chrome DevTools: recording and comparing heap snapshots to locate retained objects and detached DOM nodes
- https://developer.chrome.com/docs/devtools/memory-problems -- Chrome DevTools: end-to-end guide to diagnosing memory bloat, leaks, and frequent GC using Task Manager, Timeline, and heap tools
- https://developer.chrome.com/docs/devtools/performance/reference -- Chrome DevTools Performance panel reference: flame charts, call trees, Core Web Vitals, and runtime profiling
- https://auth0.com/blog/four-types-of-leaks-in-your-javascript-code-and-how-to-get-rid-of-them/ -- Four canonical JavaScript memory leak patterns (globals, timers, closures, detached DOM) with identification and fix strategies
