#!/usr/bin/env python

"""
Runs a standalone test on an analytics task object.
"""

import optparse
import logging
import pprint
import time
from DAS.core.das_core import DASCore

if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)

    parser = optparse.OptionParser()
    parser.add_option("-c", "--class", help="Class of task to run.", 
                      dest="klass", metavar="CLASS")
    parser.add_option("-o", "--opts", help="Dictionary of task options.")
    parser.add_option("-n", "--name", help="Name to give task.", 
                      default=None)
    parser.add_option("-i", "--id", help="ID to give task.", 
                      default=None)
    parser.add_option("-t", "--interval", help="Task interval", 
                      type="int", default=3600)

    opts, args = parser.parse_args()

    if not opts.klass:
        raise Exception("Task class required.")

    module = __import__('DAS.analytics.tasks.%s' % opts.klass, 
                        fromlist=[opts.klass])
    klass = getattr(module, opts.klass)

    if opts.name == None:
        opts.name = "CLI%s" % opts.klass
    if opts.id == None:
        opts.id = "0000000000000000"

    if opts.opts:
        opts.opts = eval(opts.opts)
    else:
        opts.opts = {}

    logger = logging.getLogger(opts.name)
    daslogger = logging.getLogger(opts.name + '_DAS')

    dascore = DASCore(logger=daslogger)

    instance = klass(logger=logger, DAS=dascore, name=opts.name,
                     taskid=opts.id, index=0, interval=opts.interval,
                     **opts.opts)

    result = instance()

    print "Return value:"
    pprint.pprint(result)

    if 'next' in result:
        print "Task requested resubmission at %s (%d sec)" % \
        (time.strftime('%H:%M', time.localtime(result['next'])),
         int(result['next']-time.time()))
    
    if 'resubmit' in result and not result['resubmit']:
        print "Task requested not to be resubmitted"
    
    if 'new_tasks' in result:
        print "Task requested the following new tasks:"
        pprint.pprint(result['new_tasks'])