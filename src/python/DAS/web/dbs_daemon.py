#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-
"""
File: dbs_daemon.py
Author: Valentin Kuznetsov <vkuznet@gmail.com>
Description: DBS daemon, which update DAS cache with DBS datasets
"""

# system modules
import re
import thread
import urllib
import urllib2
import itertools

# MongoDB modules
from pymongo.errors import InvalidOperation
from pymongo import ASCENDING

# DAS modules
import DAS.utils.jsonwrapper as json
from DAS.utils.utils import qlxml_parser
from DAS.utils.das_db import db_connection, create_indexes
from DAS.web.utils import db_monitor

class DBSDaemon(object):
    """docstring for DBSDaemon"""
    def __init__(self, dburi, dbname='dbs', dbcoll='datasets', cache_size=10000):
        self.dburi  = dburi
        self.dbname = dbname
        self.dbcoll = dbcoll
        self.cache_size = cache_size
        self.init()
        # Monitoring thread which performs auto-reconnection to MongoDB
        thread.start_new_thread(db_monitor, (dburi, self.init))

    def init(self):
        """
        Init db connection
        """
        try:
            conn = db_connection(self.dburi)
            self.col = conn[self.dbname][self.dbcoll]
            create_indexes(self.col, [('dataset', ASCENDING)])
        except Exception, _exp:
            self.col = None

    def update(self):
        """
        Update DBS collection with a fresh copy of datasets
        """
        if  self.col:
            self.col.remove()
            gen = self.datasets()
            try: # perform bulk insert operation
                while True:
                    if  not self.col.insert(itertools.islice(gen, self.cache_size)):
                        break
            except InvalidOperation:
                pass
            print "\n### DBSDaemon update is performed"

    def find(self, pattern, idx=0, limit=10):
        """
        Find datasets for a given pattern. The idx/limit parameters 
        control number of retrieved records (aka pagination). The
        limit=-1 means no pagination (get all records).
        """
        if  self.col:
            if  pattern[0] == '/':
                pattern = '^%s' % pattern
            if  pattern.find('*') != -1:
                pattern = pattern.replace('*', '.*')
            pat  = re.compile('%s' % pattern, re.I)
            spec = {'dataset':pat}
            if  limit == -1:
                for row in self.col.find(spec):
                    yield row['dataset']
            else:
                for row in self.col.find(spec).skip(idx).limit(limit):
                    yield row['dataset']

    def datasets(self):
        """
        Retrieve a list of DBS datasets (DBS2)
        """
        url = 'http://cmsdbsprod.cern.ch/cms_dbs_prod_global/servlet/DBSServlet'
        query = 'find dataset,dataset.status'
        params = {'api': 'executeQuery', 'apiversion': 'DBS_2_0_9', 'query':query}
        encoded_data = urllib.urlencode(params, doseq=True)
        url = url + '?' + encoded_data
        req = urllib2.Request(url)
        stream = urllib2.urlopen(req)
        gen = qlxml_parser(stream, 'dataset')
        for row in gen:
            if  row['dataset']['dataset.status'] == 'VALID':
                yield dict(dataset=row['dataset']['dataset'])
        stream.close()

    def dbs3_datasets(self):
        """
        Retrieve a list of DBS datasets (DBS3)
        """
        url = 'http://localhost:8989/dbs/DBSReader/datasets/'
        params = {'dataset_access_type':'PRODUCTION'}
        encoded_data = urllib.urlencode(params, doseq=True)
        url = url + '?' + encoded_data
        req = urllib2.Request(url)
        stream = urllib2.urlopen(req)
        gen = json.load(stream)
        for row in gen:
            yield row
        stream.close()
        
def test():
    uri = 'mongodb://localhost:8230'
    mgr = DBSDaemon(uri)
    mgr.update()
    idx = 0
    limit = 10
    for row in mgr.find('zee*summer', idx, limit):
        print row

if __name__ == '__main__':
    test()        
