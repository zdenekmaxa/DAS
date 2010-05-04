#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-

"""
DAS cache RESTfull model, based on WMCore/WebTools
"""

__revision__ = "$Id: DASCacheModel.py,v 1.3 2009/05/28 19:58:40 valya Exp $"
__version__ = "$Revision: 1.3 $"
__author__ = "Valentin Kuznetsov"

# system modules
import re
import types
import thread
import traceback

# WMCore/WebTools modules
from WMCore.WebTools.RESTModel import RESTModel

# DAS modules
from DAS.core.das_core import DASCore
from DAS.core.das_cache import DASCacheMgr
from DAS.utils.utils import getarg

import sys
if  sys.version_info < (2, 5):
    raise Exception("DAS requires python 2.5 or greater")

def checkargs(func):
    """Decorator to check arguments to REST server"""
    def wrapper (self, *args, **kwds):
        """Wrapper for decorator"""
        data = func (self, *args, **kwds)
        pat  = re.compile('^[+]?\d*$')
        keys = [i for i in kwds.keys() \
                    if i != 'query' and i != 'idx' \
                        and i != 'limit' and i != 'expire']
        if  keys:
            msg  = 'Unsupported keys: %s' % keys
            raise Exception(msg)
        if  not pat.match(kwds['idx']):
            msg  = 'Unsupported value idx=%s' % (kwds['idx'])
            raise Exception(msg)
        if  not pat.match(kwds['limit']):
            msg  = 'Unsupported value limit=%s' % (kwds['limit'])
            raise Exception(msg)
        pat  = re.compile('^find ')
        if  not pat.match(kwds['query']):
            msg = 'Unsupported keyword query=%s' % kwds['query']
            raise Exception(msg)
        return data
    wrapper.__doc__ = func.__doc__
    wrapper.__name__ = func.__name__
    wrapper.exposed = True
    return wrapper

def worker(item):
    """
    Worker function which invoke DAS core to update cache for input query
    """
    dascore = DASCore()
    query, expire = item
    status  = dascore.update_cache(query, expire)
    return status

class DASCacheModel(RESTModel):
    """
    Interface representing DAS cache. It is based on RESTfull model.
    It supports POST/GET/DELETE/UPDATE methods who operates with
    DAS caching systems. The input queries are placed into DAS cache
    queue and served via FIFO. DAS cache retrieve results from 
    appropriate data-service and place them into DAS cache back-end.
    All requests are placed into separate thread.
    """
    def __init__(self, config):
        # keep this line, it defines self.config which is used in WMCore
        self.config   = config 

        # define config for DASCacheMgr
        cdict         = self.config.dictionary_()
        self.dascore  = DASCore()
        sleep         = getarg(cdict, 'sleep', 2)
        verbose       = getarg(cdict, 'verbose', None)
        iconfig       = {'sleep':sleep, 'verbose':verbose}
        self.cachemgr = DASCacheMgr(iconfig)
        thread.start_new_thread(self.cachemgr.worker, (worker, ))

    @checkargs
    def handle_get(self, *args, **kwargs):
        """
        HTTP GET request.
        Retrieve results from DAS cache.
        """
        # ask for data from DAS cache, if no data found return None
        query = kwargs['query']
        idx   = getarg(kwargs, 'idx', 0)
        limit = getarg(kwargs, 'limit', 0)
        data  = {'status':'requested', 'idx':idx, 'limit':limit, 'query':query}
        if  hasattr(self.dascore, 'cache'):
            if  self.dascore.cache.incache(query):
                res = self.dascore.cache.get_from_cache(query, idx, limit)
                if  type(res) is types.GeneratorType:
                    data['result'] = [i for i in res]
                else:
                    data['result'] = res
                data['status'] = 'success'
            else:
                data['status'] = 'not found'
        else:
            data['status'] = 'no cache'
        self.debug(str(data))
        return data

    @checkargs
    def handle_post(self, *args, **kwargs):
        """
        HTTP POST request. 
        Requests the server to create a new resource
        using the data enclosed in the request body.
        Creates new entry in DAS cache for provided query.
        """
        query  = kwargs['query']
        expire = getarg(kwargs, 'expire', 600)
        data   = {'status':'requested', 'query':query, 'expire':expire}
        try:
            self.cachemgr.add(query, expire)
        except:
            data['exception'] = traceback.format_exc()
            data['status'] = 'fail'
        self.debug(str(data))
        return data

    @checkargs
    def handle_put(self, *args, **kwargs):
        """
        HTTP PUT request.
        Requests the server to replace an existing
        resource with the one enclosed in the request body.
        Replace existing query in DAS cache.
        """
        data = self.handle_delete(*args, **kwargs)
        if  data['status'] == 'success':
            data = self.handle_post(*args, **kwargs)
        else:
            data = {'status':'fail'}
        self.debug(str(data))
        return data

    @checkargs
    def handle_delete(self, *args, **kwargs):
        """
        HTTP DELETE request.
        Delete input query in DAS cache
        """
        query  = kwargs['query']
        data   = {'status':'requested', 'query':query}
        try:
            self.dascore.remove_from_cache(query)
            data = {'status':'success'}
        except:
            msg  = traceback.format_exc()
            data = {'status':'fail', 'exception':msg}
        self.debug(str(data))
        return data
