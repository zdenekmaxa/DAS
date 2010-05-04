#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-

"""
DAS couchdb wrapper. Communitate with DAS core and couchdb server(s)
"""

__revision__ = "$Id: das_couchdb.py,v 1.6 2009/04/29 15:51:57 valya Exp $"
__version__ = "$Revision: 1.6 $"
__author__ = "Valentin Kuznetsov"

import types
#from DAS.core.cmscouch import CouchServer, Database
from WMCore.Database.CMSCouch import CouchServer, Database

# DAS modules
from DAS.utils.utils import genkey, timestamp, results2couch
from DAS.core.cache import Cache

def create_views(db, design, views):
    """
    Create CouchDB views to look-up queries.
    """
    view = {}
    view['_id'] = '_design/%s' % design
    view['language'] = 'javascript' 
    view['doctype'] = 'view'
    view['views'] = views
    db.commit(view)

class DASCouchDB(Cache):
    """
    Base DAS couchdb cache class based on couchdb, see
    http://couchdb.apache.org/, The client API based on 
    http://wiki.apache.org/couchdb/Getting_started_with_Python
    in particular we use couchdb-python library
    http://couchdb-python.googlecode.com/
    """
    def __init__(self, mgr):
        Cache.__init__(self, mgr)
        uri = self.dasmgr.couch_servers # in a future I may have several
        self.uri = uri.replace('http://', '')
        self.limit = self.dasmgr.couch_lifetime
        self.server = CouchServer(self.uri)
        self.dbname = "das"
        self.cdb    = None # cached couch DB handler
        self.logger.info('Init CouchDB %s' % self.uri)

        self.views = { 
#            'query': {'map': """
#function(doc) {
#    if(doc.hash) {
#        emit(doc.hash, doc.results);
#    }
#}"""
#            },

            'query': {'map': """
function(doc) {
    if(doc.hash) {
        emit([doc.hash, doc.expire], doc.results);
    }
}"""
            },
        }

        self.adminviews = { 

            'system' : {'map': """
function(doc) {
    if(doc.results.system) {
        emit(doc.results.system, doc);
    }
}"""
            },

            'cleaner' : {'map': """
function(doc) {
    if(doc.expire) {
        emit(doc.expire, doc);
    }
}"""
            },

            'timer' : {'map': """
function(doc) {
    if(doc.timestamp) {
        emit(doc.timestamp, doc);
    }
}"""
            },

            'queries' : {'map': """
function(doc) {
    if (doc.query) {
        emit(doc.query, doc.query);
    }
}""",
                        'reduce': """
/* http://mail-archives.apache.org/mod_mbox/couchdb-user/200903.mbox/browser */
function(k,v,r) {
        function unique_inplace(an_array) {
                var first = 0;
                var last = an_array.length;
                // Find first non-unique pair
                for(var firstb; (firstb = first) < last && ++first < last; ) {
                        if(an_array[firstb] == an_array[first]) {
                                // Start copying, skipping uniques
                                for(; ++first < last; ) {
                                        if (!(an_array[firstb] == an_array[first])) {
                                                an_array[++firstb] = an_array[first];
                                        }
                                }
                                // firstb is at the last element of the new array
                                ++firstb;
                                an_array.length = firstb;
                                return;
                        }
                }
        }

        if(r) {
                var arr=[];
                for (var i=0; i<v.length; i++) {
                        arr=arr.concat(v[i]);
                }
                arr=arr.sort();
                unique_inplace(arr);
                return(arr);
        } else {
                var arr=v.sort();
                unique_inplace(arr);
                return(arr);
        }
}
"""
            }
        }

    def dbinfo(self, dbname):
        """
        Provide couch db info
        """
        cdb = self.couchdb(dbname)
        if  cdb:
            self.logger.info(cdb.info())
        else:
            self.logger.warning("No '%s' found in couch db" % dbname)

    def delete(self, dbname, system=None):
        """
        Delete couch db
        """
        cdb = self.couchdb(dbname)
        if  cdb:
            if  system:
                key = '"%s"' % system
                options = {'key' : key}
                results = self.get_view('dasadmin', 'system', options)
                for doc in results:
                    cdb.queuedelete(doc)
                cdb.commit()
            else:
                self.server.deleteDatabase(dbname)
        return

    def couchdb(self, dbname):
        """
        look up db in couch db server, if found give it back to user
        """
        if  self.cdb:
            return self.cdb
        couch_db_list = []
        try:
            couch_db_list = self.server.listDatabases()
        except:
            return None
        if  dbname not in couch_db_list:
            self.logger.info("DASCouchDB::couchdb, create db %s" % dbname)
            cdb = self.server.createDatabase(dbname)
            create_views(cdb, 'dasviews', self.views)
            create_views(cdb, 'dasadmin', self.adminviews)
        else:
            self.logger.info("DASCouchDB::couchdb, connect db %s" % dbname)
            cdb = self.server.connectDatabase(dbname)
        self.cdb = cdb
        return cdb

    def get_from_cache(self, query):
        """
        Retreieve results from cache, otherwise return null.
        """
        dbname = self.dbname
        cdb = self.couchdb(dbname)
        if  not cdb:
            return
        key  = genkey(query)

        skey = '["%s", %s ]' % (key, timestamp())
        ekey = '["%s", %s ]' % (key, 9999999999)
        options = {'startkey': skey, 'endkey': ekey}
        results = cdb.loadview('dasviews', 'query', options)

#        options = {'key': '"%s"' % key}
#        results = cdb.loadview(self.design, 'query', options)

        try:
            res = [row['value'] for row in results['rows']]
        except:
            traceback.print_exc()
            return
        if  res:
            self.logger.info("DASCouchDB::get_from_cache for %s" % query)
        if  len(res) == 1:
            return res[0]
        return res

    def update_cache(self, query, results, expire):
        """
        Insert results into cache. We use bulk insert operation, 
        db.update over entire set, rather looping for every single 
        row and use db.create. The speed up is factor of 10
        """
        self.logger.info("DASCouchDB::update_cache for %s" % query)
        if  not results:
            return
        dbname = self.dbname
        cdb = self.couchdb(dbname)
        if  not cdb:
            return
        if  type(results) is types.ListType:
            for row in results:
                res = results2couch(query, row, expire)
                cdb.queue(res)
        else:
            res = results2couch(query, results, expire)
            cdb.queue(res)
        cdb.commit()

    def get_view(self, design, view, options={}):
        """
        Retreieve results from cache based on provided CouchDB view
        """
        dbname = self.dbname
        cdb = self.couchdb(dbname)
        if  not cdb:
            return
        results = cdb.loadview(design, view, options)
        res = [row['value'] for row in results['rows']]
        if  len(res) == 1:
            return res[0]
        return res

    def list_views(self):
        """
        Return a list of CouchDB views
        """

    def clean_cache(self):
        """
        Clean expired docs in couch db.
        """
        dbname = self.dbname
        cdb = self.couchdb(dbname)
#        print "+++CALL das_couch::clean_cache", dbname, cdb
        if  not cdb:
            return
        skey = '%s' % 0
        ekey = '%s' % timestamp()
        options = {'startkey': skey, 'endkey': ekey}
        results = cdb.loadview(self.design, 'cleaner', options)

        ndocs = 0
        for doc in results['rows']:
            cdb.queuedelete(doc['value'])
            ndocs += 1

        self.logger.info("DASCouchDB::clean_couch, will remove %s doc's" \
            % ndocs )

        cdb.commit()  # bulk delete
        cdb.compact() # remove them permanently
        
    def create_ft_index(self, db, name):
        view = client.PermanentView(self.uri, name)
        key = '_design/%s' % name
        db[key] = { 'language': 'javascript',
                    'ft_index': 
"""function(doc) { 
if(doc.body) index(doc.body); 
if(doc.foo) property("foo", doc.foo);
}"""
                  }