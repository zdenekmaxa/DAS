#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-
"""
File: request_manager.py
Author: Valentin Kuznetsov <vkuznet@gmail.com>
Description: Persistent request manager for DAS web server
"""

# system modules
import time
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

# DAS modules
import DAS.utils.jsonwrapper as json
from DAS.utils.das_db import db_connection
from DAS.utils.das_db import create_indexes
from DAS.utils.utils import print_exc, dastimestamp

class RequestManager(object):
    """
    RequestManager holds information about DAS requests. It stores
    pid/kwds pairs into MongoDB, where we assign MongoDB _id to be
    equal to pid (to avoid creating a new index). Since MongoDB
    does not support storage of 'key.attr' as a dict key, we use
    json dumps/loads method to serialize kwds.
    """
    def __init__(self, dburi, dbname='das', dbcoll='requests', lifetime=86400):
        self.con  = db_connection(dburi)
        self.col  = self.con[dbname][dbcoll]
        self.hold = self.con[dbname][dbcoll + '_onhold']
        create_indexes(self.col , [('ts', ASCENDING)])
        create_indexes(self.hold, [('ts', ASCENDING)])
        self.lifetime = lifetime # default 1 hour

    def clean(self):
        """Clean on hold collection"""
        self.col.remove({'ts':{'$lt':time.time()-self.lifetime}})

    def get(self, pid):
        """Get params for a given pid"""
        doc = self.col.find_one(dict(_id=pid))
        if  doc and isinstance(doc, dict):
            return json.loads(doc['kwds'])
        
    def add(self, pid, kwds):
        """Add new pid/kwds"""
        self.clean()
        if  not kwds:
            return
        tstamp = time.strftime("%Y%m%d %H:%M:%S", time.localtime())
        doc = dict(_id=pid, kwds=json.dumps(kwds),
                ts=time.time(), timestamp=tstamp)
        attempts = 0
        while True:
            try:
                self.col.insert(doc, safe=True)
                break
            except DuplicateKeyError as err:
                break
            except Exception as err:
                print_exc(err)
                time.sleep(0.01)
            attempts += 1
            if  attempts > 2:
                msg = '%s unable to add pid=%s' % (self.col, pid)
                print dastimestamp('DAS ERROR '), msg
                break
        
    def remove(self, pid):
        """Remove given pid"""
        self.clean()
        attempts = 0
        while True:
            try:
                self.col.remove(dict(_id=pid), safe=True)
                break
            except Exception as err:
                print_exc(err)
                time.sleep(0.01)
            attempts += 1
            if  attempts > 2:
                msg = '%s unable to remove pid=%s' % (self.col, pid)
                print dastimestamp('DAS ERROR '), msg
                break
        
    def items(self):
        """Return list of current requests"""
        self.clean()
        for row in self.col.find():
            row['_id'] = str(row['_id'])
            yield row

    def add_onhold(self, pid, uinput, addr, future_tstamp):
        """Add user input to onhold collection"""
        tstamp = time.strftime("%Y%m%d %H:%M:%S", time.localtime())
        doc = dict(_id=pid, ip=addr, uinput=uinput, \
                        ts=future_tstamp, timestamp=tstamp)
        try:
            self.hold.insert(doc, safe=True)
        except DuplicateKeyError:
            pass
        except Exception as err:
            print_exc(err)

    def remove_onhold(self, pid):
        """Remove pid item from onhold collection"""
        self.hold.remove({'_id':pid})

    def items_onhold(self):
        """Return list of current onhold requests"""
        for row in self.hold.find({'ts':{'$lte':time.time()}}):
            row['_id'] = str(row['_id'])
            yield row

    def has_pid(self, pid):
        """Return true/false for requested pid"""
        return self.col.find_one({'_id':pid})

    def size(self):
        """Return size of the request cache"""
        self.clean()
        return self.col.count()
