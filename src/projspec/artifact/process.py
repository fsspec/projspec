import io
import logging
import os
from queue import Queue, Empty
import re
import subprocess
import sys
from threading import Thread
import time
import weakref

from projspec.artifact import BaseArtifact


logger = logging.getLogger("projspec")

ON_POSIX = "posix" in sys.builtin_module_names


def _enqueue(out: io.IOBase, queue: Queue[bytes]):
    """Reads subprocess output in a separate thread to prevent deadlocks"""
    while True:
        if line := out.readline():
            logger.debug(line.decode("utf-8").rstrip())
            queue.put(line)
        else:
            break


class Process(BaseArtifact):
    """A simple process where we know nothing about what it does, only if it's running.

    Can include batch jobs and long-running services.
    """

    term: bool = False
    environ: dict[str, str] = {}
    queue: Queue[bytes] | None = None  # lines of binary output by the subprocess

    def _make(self, **kwargs):
        if self.environ and "environ" not in kwargs:
            env = os.environ.copy()
            env.update(self.environ)
            kwargs["env"] = env
        if self.proc is None:
            self.queue = Queue()
            logger.info(f"Running {self.cmd}")
            proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.proj.url,
                close_fds=ON_POSIX,
                **kwargs,
            )
            # should be optional?
            t = Thread(target=_enqueue, args=(proc.stdout, self.queue))
            t.daemon = True  # thread dies with the program
            t.start()
            if self.term:
                weakref.finalize(self, proc.terminate)
                # weakref.finalize(self, t.join)
            self.proc = proc

    def _is_done(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def clean(
        self,
    ):
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()
            self.proc = None
            self.queue = None


class Server(Process):
    """A process that is designed to stay running and serve requests, usually over HTTP

    When calling make(), some instances will accept port= and address= arguments
    to specify listening, but only if the instance was initially configured with
    port_arg= and address_arg=.

    After creating the process, is scan is True, the actual listening address and port
    will attempt to be inferred.
    """

    _port: int = 0
    _address: str = "0.0.0.0"
    _url_pattern: str = re.compile(r".*http[s]?://([^:]+):(\d+)")
    scan: bool = True
    port_arg: str | None = None
    address_arg: str | None = None
    in_env: bool = False

    def _make(self, port: int | None = None, address: str | None = None, **kwargs):
        cmd = self.cmd[:]
        if port is not None and self.port_arg is not None:
            self._port = port
            if self.in_env:
                self.environ[self.port_arg] = str(port)
            else:
                self.cmd.extend([self.port_arg, str(port)])
        if address is not None and self.address_arg is not None:
            self._address = address
            if self.in_env:
                self.environ[self.address_arg] = address
            else:
                self.cmd.extend([self.address_arg, address])

        super()._make()
        self.cmd = cmd
        if self.scan and (port is None or address is None):
            t0 = time.time()
            while True:
                if time.time() - t0 > 2:
                    break
                try:
                    line = self.queue.get_nowait().decode("utf-8")
                except Empty:
                    time.sleep(0.02)
                    continue
                if not line:
                    break
                if match := self._url_pattern.match(line):
                    self._address = address or match.group(1)
                    self._port = int(match.group(2)) if port is None else port
                    break
