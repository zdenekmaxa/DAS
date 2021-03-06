#!/usr/bin/python
#pylint: disable-msg=W0141
"""
Task manager

spawn(func, \*args) to spawn execution of given func(args)
is_alive(pid) return status of executing job
joinall() to join all tasks in a queue and exiting existing workers
join(jobs) to join all tasks without stopping workers
"""

# system modules
from cherrypy.process import plugins
from threading import Thread, Event
from Queue import Queue

# DAS modules
from DAS.utils.utils import genkey, print_exc

class Worker(Thread):
    """Thread executing worker from a given tasks queue"""
    def __init__(self, name, taskq, pidq):
        Thread.__init__(self, name=name)
        self.exit   = 0
        self._tasks = taskq
        self._pids  = pidq
        self.daemon = True
        self.start()

    def force_exit(self):
        """Force run loop to exit in a hard way"""
        self.exit   = 1

    def run(self):
        """Run thread loop."""
        while True:
            if  self.exit:
                return
            task = self._tasks.get()
            if  task == None:
                return
            evt, pid, func, args, kwargs = task
            try:
                func(*args, **kwargs)
                self._pids.discard(pid)
            except Exception as err: 
                self._pids.discard(pid)
                print_exc(err)
            evt.set()

class TaskManager:
    """
    Task manager class based on thread module which
    executes assigned tasks concurently. It uses a 
    pool of thread workers, queue of tasks and pid 
    set to monitor jobs execution.

    .. doctest::

        Use case:
        mgr  = TaskManager()
        jobs = []
        jobs.append(mgr.spaw(func, args))
        mgr.joinall(jobs)

    """
    def __init__(self, nworkers=10, name='TaskManager', debug=0):
        self.name   = name
        self.debug  = debug
        self._pids  = set()
        self._tasks = Queue()
        self._workers = [Worker(name, self._tasks, self._pids) \
                        for _ in xrange(0, nworkers)]

    def nworkers(self):
        """Return number of workers associated with this manager"""
        return len(self._workers)

    def spawn(self, func, *args, **kwargs):
        """Spawn new process for given function"""
        pid = kwargs.get('pid', genkey(str(args) + str(kwargs)))
        if  not pid in self._pids:
            self._pids.add(pid)
            ready = Event()
            self._tasks.put((ready, pid, func, args, kwargs))
            return ready, pid
        else:
            return 'in set', pid

    def remove(self, pid):
        """Remove pid and associative process from the queue"""
        self._pids.discard(pid)

    def is_alive(self, pid):
        """Check worker queue if given pid of the process is still running"""
        return pid in self._pids 

    def clear(self, tasks):
        """
        Clear all tasks in a queue. It allows current jobs to run, but will
        block all new requests till workers event flag is set again
        """
        map(lambda (evt, pid): (evt.clear(), pid), tasks)

    def joinall(self, tasks):
        """Join all tasks in a queue and quite"""
        map(lambda (evt, pid): (evt.wait(), pid), tasks)

    def quit(self):
        """Put None task to all workers and let them quit"""
        map(lambda w: self._tasks.put(None), self._workers)
        map(lambda w: w.join(), self._workers)

    def force_exit(self):
        """Force all workers to exit"""
        map(lambda w: w.force_exit(), self._workers)

class PluginTaskManager(TaskManager, plugins.SimplePlugin):
    """
    PluginTaksManager add start/stop/graceful functionality
    to base TaskManager class for provided bus engine, e.g. 
    cherrypy.engine
    """
    def __init__(self, bus, nworkers=10, name='PluginTaskManager', debug=0):
        plugins.SimplePlugin.__init__(self, bus)
        TaskManager.__init__(self, nworkers, name, debug)
        if  debug:
            print "%s init with %s workers" % (name, nworkers)

    def start(self):
        """
        Implementation for external bus, e.g. cherrypy.engine.
        When external bus will start this method will be invoked.
        """
        if  self.debug:
            print "%s start" % self.name

    def stop(self):
        """
        Implementation for external bus, e.g. cherrypy.engine.
        When external bus will stop this method will be invoked.
        """
        if  self.debug:
            print "%s stop" % self.name
        self.force_exit()

    def exit(self):
        """
        Implementation for external bus, e.g. cherrypy.engine.
        When external bus will exit this method will be invoked.
        """
        if  self.debug:
            print "%s exit" % self.name
        self.stop()

    def graceful(self):
        """
        Implementation for external bus, e.g. cherrypy.engine.
        When external bus will stop this method will be invoked.
        """
        if  self.debug:
            print "%s graceful" % self.name
        self.quit()

