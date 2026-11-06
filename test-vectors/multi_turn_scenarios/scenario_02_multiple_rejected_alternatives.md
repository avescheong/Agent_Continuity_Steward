# Scenario 02: Multiple Rejected Alternatives

Human:
We need to select an IPC mechanism between the Windows desktop UI and Python core daemon.

AI:
Here are three candidates:
1. Local HTTP REST on loopback port.
2. Shared memory via memory-mapped files.
3. Windows Named Pipes.

Human:
Do not use Local HTTP because port conflicts with existing developer servers.
Do not use Shared Memory because mutex synchronization in Python is brittle.
Let's use Windows Named Pipes because it is native and has zero port conflict.
