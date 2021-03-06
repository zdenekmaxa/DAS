#!/usr/bin/env python

"""
DAS benchmark tool
"""

import os
import re
import copy
import math
import string
import random
import urllib
import urllib2
import traceback

from   json import JSONDecoder
from   random import Random
from   optparse import OptionParser
from   multiprocessing import Process

try:
    import matplotlib.pyplot as plt
except:
    pass

class NClientsOptionParser: 
    """client option parser"""
    def __init__(self):
        self.parser = OptionParser()
        self.parser.add_option("-v", "--verbose", action="store", 
                               type="int", default=0, dest="debug",
             help="verbose output")
        self.parser.add_option("--url", action="store", type="string", 
                               default="", dest="url",
             help="specify URL to test, e.g. http://localhost:8211/rest/test")
        self.parser.add_option("--accept", action="store", type="string", 
                               default="application/json", dest="accept",
             help="specify URL Accept header, default application/json")
        self.parser.add_option("--idx-bound", action="store", type="long", 
                               default=0, dest="idx",
             help="specify index bound, by default it is 0")
        self.parser.add_option("--logname", action="store", type="string", 
                               default='spammer', dest="logname",
        help="specify log name prefix where results of N client \
                test will be stored")
        self.parser.add_option("--nclients", action="store", type="int", 
                               default=10, dest="nclients",
             help="specify max number of clients")
        self.parser.add_option("--dasquery", action="store", type="string", 
                               default="dataset", dest="dasquery",
             help="specify DAS query to test, e.g. dataset")
        self.parser.add_option("--pdf", action="store", type="string", 
                               default="results.pdf", dest="pdf",
        help="specify name of PDF file for matplotlib output, \
                default is results.pdf")
    def get_opt(self):
        """Returns parse list of options"""
        return self.parser.parse_args()

### Natural sorting utilities
def try_int(sss):
    "Convert to integer if possible."
    try:
        return int(sss)
    except:
        return sss

def natsort_key(sss):
    "Used internally to get a tuple by which s is sorted."
    return map(try_int, re.findall(r'(\d+|\D+)', sss))

def natcmp(aaa, bbb):
    "Natural string comparison, case sensitive."
    return cmp(natsort_key(aaa), natsort_key(bbb))

def natcasecmp(aaa, bbb):
    "Natural string comparison, ignores case."
    return natcmp(aaa.lower(), bbb.lower())

def natsort(seq, cmp=natcmp):
    "In-place natural string sort."
    seq.sort(cmp)
    
def natsorted(seq, cmp=natcmp):
    "Returns a copy of seq, sorted by natural string sort."
    temp = copy.copy(seq)
    natsort(temp, cmp)
    return temp

def gen_passwd(length=8, chars=string.letters + string.digits):
    """
    Random string generator, code based on
    http://code.activestate.com/recipes/59873-random-password-generation/
    """
    return ''.join( Random().sample(chars, length) )

def random_index(bound):
    """Generate random number for given upper bound"""
    return long(random.random()*bound)

### URL utilities
class UrlRequest(urllib2.Request):
    """
    URL requestor class which supports all RESTful request methods.
    It is based on urllib2.Request class and overwrite request method.
    Usage: UrlRequest(method, url=url, data=data), where method is
    GET, POST, PUT, DELETE.
    """
    def __init__(self, method, *args, **kwargs):
        self._method = method
        urllib2.Request.__init__(self, *args, **kwargs)

    def get_method(self):
        """Return request method"""
        return self._method

def urlrequest(stream, url, headers, debug=0):
    """URL request function"""
    if  debug:
        print "Input for urlrequest", url, headers, debug
    req      = UrlRequest('GET', url=url, headers=headers)
    if  debug:
        hdlr     = urllib2.HTTPHandler(debuglevel=1)
        opener   = urllib2.build_opener(hdlr)
    else:
        opener   = urllib2.build_opener()
    fdesc    = opener.open(req)
    data     = fdesc.read()
    fdesc.close()
    decoder  = JSONDecoder()
    response = decoder.decode(data)
    if  isinstance(response, dict):
        stream.write(str(response) + '\n')
    stream.flush()

def spammer(stream, host, method, params, headers, debug=0):
    """Spammer function"""
    path     = method
    if  host.find('http://') == -1:
        host = 'http://' + host
    encoded_data = urllib.urlencode(params, doseq=True)
    if  encoded_data:
        url  = host + path + '?%s' % encoded_data
    else:
        url  = host + path
    proc = Process(target=urlrequest, args=(stream, url, headers, debug))
    proc.start()
    return proc

def runjob(nclients, host, method, params, headers, idx, limit,
           debug=0, logname='spammer', dasquery=None):
    """
    Run spammer for provided number of parralel clients, host name
    and method (API). The output data are stored into lognameN.log,
    where logname is an optional parameter with default as spammer.
    """
    stream     = open('%s%s.log' % (logname, nclients), 'w')
    processes  = []
    for _ in range(0, nclients):
        if  dasquery:
            ### REPLACE THIS PART with your set of parameter
            if  dasquery.find('=') == -1:
                query  = '%s=/%s*' % (dasquery, gen_passwd(1, string.letters))
            else:
                query  = dasquery
            params = {'query':query, 'idx':random_index(idx), 'limit':limit} 
            if  method == '/rest/testmongo':
                params['collection'] = 'das.merge'
            ###
        proc   = spammer(stream, host, method, params, headers, debug)
        processes.append(proc)
    while True:
        if  not processes:
            break
        for proc in processes:
            if  proc.exitcode != None:
                processes.remove(proc)
                break
    stream.close()

def avg_std(input_file):
    """Calculate average and standard deviation"""
    count = 0
    sum   = 0
    arr   = []
    with open(input_file) as input_data:
        for line in input_data.readlines():
            if  not line:
                continue
            data = {}
            try:
                data = eval(line.replace('\n', ''))
            except:
                print "In file '%s' fail to process line='%s'" \
                        % (input_file, line)
                traceback.print_exc()
                continue
            if  data.has_key('ctime'):
                res    = float(data['ctime'])
                sum   += res
                count += 1
                arr.append(res)
    if  count:
        mean = sum/count
        std2 = 0
        for item in arr:
            std2 += (mean - item)**2
        return (mean, math.sqrt(std2/count))
    else:
        msg = 'Unable to count results'
        raise Exception(msg)

def make_plot(xxx, yyy, std=None, name='das_cache.pdf', 
              xlabel='Number of clients', ylabel='Time/request (sec)',
              yscale=None):
    """Make standard plot time vs nclients using matplotlib"""
    plt.plot(xxx, yyy, 'ro-')
    plt.grid(True)
    if  yscale:
        plt.yscale('log')
    plt.axis([min(xxx)-1, max(xxx)+5, min(yyy)-5, max(yyy)+5])
    if  std:
        plt.errorbar(xxx, yyy, yerr=std)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.savefig(name, format='pdf', transparent=True)
    plt.close()

def main():
    """Main routine"""
    mgr = NClientsOptionParser()
    (opts, args) = mgr.get_opt()

    url = opts.url.replace('?', ';').replace('&amp;', ';').replace('&', ';')
    logname  = opts.logname
    dasquery = opts.dasquery
    idx      = opts.idx
    limit    = 1
    nclients = opts.nclients
    debug    = opts.debug
    headers  = {'Accept': opts.accept}
    urlpath, args = urllib.splitattr(url)
    arr      = urlpath.split('/')
    if  arr[0] == 'http:' or arr[0] == 'https:':
        host = arr[0] + '//' + arr[2]
    else:
        msg  = 'Provided URL="%s" does not contain http:// part' % opts.url
        raise Exception(msg)
    method   = '/' + '/'.join(arr[3:])
    params   = {}
    for item in args:
        key, val = item.split('=')
        params[key] = val

    # do clean-up
    for filename in os.listdir('.'):
        if  filename.find('.log') != -1 and filename.find(logname) != -1:
            os.remove(filename)

    # perform action
    array = []
    if  nclients <= 10:
        array += range(1, nclients+1)
    if  nclients <= 100 and nclients > 10:
        array  = range(1, 10)
        array += range(10, nclients+1, 10)
    if  nclients <= 1000 and nclients > 100:
        array  = range(1, 10)
        array += range(10, 100, 10)
        array += range(100, nclients+1, 100)

    for nclients in array:
        print "Run job with %s clients" % nclients
        runjob(nclients, host, method, params, headers, idx, limit, 
               debug, logname, dasquery)

    # analyze results
    file_list = []
    for filename in os.listdir('.'):
        if  filename.find('.log') != -1:
            file_list.append(filename)
    xxx = []
    yyy = []
    std = []
    for file in natsorted(file_list):
        name, _ = file.split('.')
        xxx.append(int(name.split(logname)[-1]))
        mean, std2 = avg_std(file)
        yyy.append(mean)
        std.append(std2)
    try:
        make_plot(xxx, yyy, std, opts.pdf)
    except:
        print "xxx =", xxx
        print "yyy =", yyy
        print "std =", std

if __name__ == '__main__':
    main()

