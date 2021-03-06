#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-
#pylint: disable-msg=W0703,R0913,R0912,R0914,R0915,R0902,R0903,R0904

"""
DAS mongocache manager.
The DAS consists of several sub-systems:

    - DAS cache contains data records (output from data-services)
      and API records
    - DAS merge contains merged data records
    - DAS mapreduce collection
"""

__revision__ = "$Id: das_mongocache.py,v 1.86 2010/05/03 19:14:06 valya Exp $"
__version__ = "$Revision: 1.86 $"
__author__ = "Valentin Kuznetsov"

import time
from   types import GeneratorType
import datetime
import itertools
import fnmatch

# DAS modules
from DAS.core.das_son_manipulator import DAS_SONManipulator
from DAS.core.das_query import DASQuery
from DAS.utils.query_utils import decode_mongo_query
from DAS.utils.ddict import convert_dot_notation
from DAS.utils.utils import aggregator, unique_filter
from DAS.utils.utils import adjust_mongo_keyvalue, print_exc, das_diff
from DAS.utils.utils import parse_filters, expire_timestamp
from DAS.utils.utils import dastimestamp
from DAS.utils.das_db import db_connection
from DAS.utils.das_db import db_gridfs, parse2gridfs, create_indexes
from DAS.utils.logger import PrintManager

# monogo db modules
from pymongo.objectid import ObjectId
from pymongo.code import Code
from pymongo import DESCENDING, ASCENDING
from pymongo.errors import InvalidOperation
from bson.errors import InvalidDocument
from pymongo.errors import OperationFailure

def update_query_spec(spec, fdict):
    """
    Update spec dict with given dictionary. If fdict
    keys overlap with spec dict, we construct and $and condition.
    Please note we update given query spec!!!
    """
    keys = spec.keys()
    and_list = spec.get('$and', None)
    if  set(keys) & set(fdict.keys()):
        for key, val in fdict.iteritems():
            if  key in keys:
                qvalue = spec[key]
                if  isinstance(qvalue, list):
                    qvalue.add({key:val})
                    cond = {'$and' : qvalue}
                else:
                    cond = {'$and' : [{key:qvalue}, {key:val}]}
                del spec[key]
                spec.update(cond)
            else:
                spec.update({key:val})
    elif and_list:
        for key, val in fdict.iteritems():
            if  key in [k for d in and_list for k in d.keys()]:
                and_list.append({key:val})
            else:
                spec.update({key:val})
    else: # set of keys do not overlap
        spec.update(fdict)

def adjust_id(query):
    """
    We need to adjust input query who has '_id' as a string to ObjectId
    used in MongoDB.
    """
    spec = query['spec']
    if  spec.has_key('_id'):
        val = spec['_id']
        if  isinstance(val, str):
            newval = ObjectId(val)
            spec['_id'] = newval
        elif isinstance(val, unicode):
            newval = ObjectId(unicode.encode(val))
            spec['_id'] = newval
        elif isinstance(val, list):
            newval = []
            for item in val:
                if  isinstance(item, str):
                    newval.append(ObjectId(item))
                elif isinstance(item, unicode):
                    newval.append(ObjectId(unicode.encode(item)))
                else:
                    raise Exception('Wrong type for id, %s=%s' \
                        % (item, type(item)))
            spec['_id'] = newval
        query['spec'] = spec
    return query

def logdb_record(coll, doc):
    "Return logdb record"
    timestamp = time.time()
    date = int(str(datetime.date.fromtimestamp(time.time())).replace('-', ''))
    rec = {'type':coll, 'date':date, 'ts':timestamp}
    rec.update(doc)
    return rec

class DASLogdb(object):
    """DASLogdb"""
    def __init__(self, config):
        super(DASLogdb, self).__init__()
        capped_size = config['loggingdb']['capped_size']
        logdbname   = config['loggingdb']['dbname']
        logdbcoll   = config['loggingdb']['collname']
        dburi       = config['mongodb']['dburi']
        try:
            conn    = db_connection(dburi)
            if  logdbname not in conn.database_names():
                dbname      = conn[logdbname]
                dbname.create_collection('db', capped=True, size=capped_size)
                print 'Created %s.%s, size=%s' \
                % (logdbname, logdbcoll, capped_size)
            self.logcol     = conn[logdbname][logdbcoll]
        except Exception as exc:
            print_exc(exc)
            self.logcol     = None

    def insert(self, coll, doc):
        "Insert record to logdb"
        if  self.logcol:
            rec = logdb_record(coll, doc)
            self.logcol.insert(rec)

    def find(self, spec, count=False):
        "Find record in logdb"
        if  self.logcol:
            if  count:
                return self.logcol.find(spec).count()
            return self.logcol.find(spec)
        return False

class DASMongocache(object):
    """
    DAS cache based MongoDB. 
    """
    def __init__(self, config):
        self.emptyset_expire = expire_timestamp(\
            config['das'].get('emptyset_expire', 5))
        self.dburi   = config['mongodb']['dburi']
        self.cache_size = config['mongodb']['bulkupdate_size']
        self.dbname  = config['dasdb']['dbname']
        self.verbose = config['verbose']
        self.logger  = PrintManager('DASMongocache', self.verbose)
        self.mapping = config['dasmapping']

        self.conn    = db_connection(self.dburi)
        self.mdb     = self.conn[self.dbname]
        self.col     = self.mdb[config['dasdb']['cachecollection']]
        self.mrcol   = self.mdb[config['dasdb']['mrcollection']]
        self.merge   = self.mdb[config['dasdb']['mergecollection']]
        self.gfs     = db_gridfs(self.dburi)

        self.logdb   = DASLogdb(config)

        self.das_internal_keys = ['das_id', 'das', 'cache_id', 'qhash']

        msg = "%s@%s" % (self.dburi, self.dbname)
        self.logger.info(msg)

        self.add_manipulator()

        # ensure that we have the following indexes
        index_list = [('das.expire', ASCENDING), ('das_id', ASCENDING),
                      ('das.system', ASCENDING),
                      ('qhash', DESCENDING),
                      ('das.empty_record', ASCENDING)]
        create_indexes(self.col, index_list)
        index_list = [('das.expire', ASCENDING), ('das_id', ASCENDING),
                      ('qhash', DESCENDING),
                      ('das.empty_record', ASCENDING), ('das.ts', ASCENDING)]
        create_indexes(self.merge, index_list)
        
    def add_manipulator(self):
        """
        Add DAS-specific MongoDB SON manipulator to perform
        conversion of inserted data into DAS cache.
        """
        das_son_manipulator = DAS_SONManipulator()
        self.mdb.add_son_manipulator(das_son_manipulator)
        msg = "DAS_SONManipulator %s" \
        % das_son_manipulator
        self.logger.debug(msg)

    def similar_queries(self, dasquery):
        """
        Check if we have query results in cache whose conditions are
        superset of provided query. The method only works for single
        key whose value is substring of value in input query.
        For example, if cache contains records about T1 sites, 
        then input query T1_CH_CERN is subset of results stored in cache.
        """
        spec = dasquery.mongo_query.get('spec', {})
        cond = {'query.spec.key': {'$in' : spec.keys()}, 'qhash':dasquery.qhash}
        for row in self.col.find(cond):
            found_query = DASQuery(row['query'])
            if  dasquery.qhash == found_query.qhash:
                msg = "%s similar to %s" % (dasquery, found_query)
                self.logger.info(msg)
                return found_query
        return False
    
    def get_superset_keys(self, key, value):
        """
        This is a special-case version of similar_keys,
        intended for analysers that want to quickly
        find possible superset queries of a simple
        query of the form key=value.
        """
        
        msg = "%s=%s" % (key, value)
        self.logger.debug(msg)
        cond = {'query.spec.key': key}
        for row in self.col.find(cond):
            mongo_query = decode_mongo_query(row['query'])
            for thiskey, thisvalue in mongo_query.iteritems():
                if thiskey == key:
                    if fnmatch.fnmatch(value, thisvalue):
                        yield thisvalue

    def get_fields(self, dasquery):
        "Prepare fields to extract from MongoDB"
        fields     = dasquery.mongo_query.get('fields', None)
        if  fields == ['records']:
            fields = None # look-up all records
        filters    = dasquery.filters
        cond       = {}
        if  filters:
            new_fields = []
            for dasfilter in filters:
                if  dasfilter == 'unique':
                    continue
                if  dasfilter not in fields and \
                    dasfilter not in new_fields:
                    if  dasfilter.find('=') == -1 and dasfilter.find('<') == -1\
                    and dasfilter.find('>') == -1:
                        new_fields.append(dasfilter)
                    else:
                        cond = parse_filters(dasquery.mongo_query)
            if  not new_fields and fields:
                new_fields = list(fields)
            return new_fields, cond
        return fields, cond

    def remove_expired(self, collection):
        """
        Remove expired records from DAS cache.
        """
        timestamp = int(time.time())
        col  = self.mdb[collection]
        spec = {'das.expire' : {'$lt' : timestamp}}
        if  self.verbose:
            nrec = col.find(spec).count()
            msg  = "will remove %s records" % nrec
            msg += ", localtime=%s" % timestamp
            self.logger.debug(msg)
        self.logdb.insert(collection, {'delete': self.col.find(spec).count()})
        col.remove(spec)

    def find(self, dasquery):
        """
        Find provided query in DAS cache.
        """
        cond = {'qhash': dasquery.qhash, 'das.system':'das'}
        return self.col.find_one(cond)

    def find_specs(self, dasquery, system='das'):
        """
        Check if cache has query whose specs are identical to provided query.
        Return all matches.
        """
        cond = {'qhash': dasquery.qhash}
        if  system:
            cond.update({'das.system': system})
        return self.col.find(cond)

    def get_das_ids(self, dasquery):
        """
        Return list of DAS ids associated with given query
        """
        das_ids = []
        try:
            das_ids = \
                [r['_id'] for r in self.col.find_specs(dasquery, system='')]
        except:
            pass
        return das_ids

    def update_das_expire(self, dasquery, timestamp):
        "Update timestamp of all DAS data records for given query"
        nval = {'$set': {'das.expire':timestamp}}
        spec = {'qhash' : dasquery.qhash}
        self.col.update(spec, nval, multi=True, safe=True)
        self.merge.update(spec, nval, multi=True, safe=True)

    def das_record(self, dasquery):
        "Retrieve DAS record for given query"
        return self.col.find_one({'qhash': dasquery.qhash})
    
    def find_records(self, das_id):
        " Return all the records matching a given das_id"
        return self.col.find({'das_id': das_id})

    def add_to_record(self, dasquery, info, system=None):
        "Add to existing DAS record provided info"
        if  system:
            self.col.update({'query': dasquery.storage_query,
                             'das.system':system},
                            {'$set': info}, upsert=True, safe=True)
        else:
            self.col.update({'query': dasquery.storage_query},
                            {'$set': info}, upsert=True, safe=True)

    def update_query_record(self, dasquery, status, header=None):
        "Update DAS record for provided query"
        if  header:
            system = header['das']['system']
            spec1  = {'qhash': dasquery.qhash, 'das.system': 'das'}
            dasrecord = self.col.find_one(spec1)
            spec2  = {'qhash': dasquery.qhash, 'das.system': system}
            sysrecord = self.col.find_one(spec2)
            hexpire = header['das']['expire']
            dexpire = hexpire
            if  dasrecord and dasrecord.has_key('das'):
                dexpire = dasrecord['das'].get('expire', None)
            if  dexpire and hexpire > dexpire:
                expire = dexpire
            else:
                expire = hexpire
            if  sysrecord:
                api  = header['das']['api']
                url  = header['das']['url']
                sapi = sysrecord['das'].get('api', [])
                surl = sysrecord['das'].get('url', [])
                if  set(api) & set(sapi) == set(api) and \
                    set(url) & set(surl) == set(url):
                    self.col.update({'_id':ObjectId(sysrecord['_id'])},
                        {'$set': {'das.expire':expire, 'das.status':status}},
                        safe=True)
                else:
                    self.col.update({'_id':ObjectId(sysrecord['_id'])},
                        {'$pushAll':{'das.api':header['das']['api'],
                                     'das.urn':header['das']['api'],
                                     'das.url':header['das']['url'],
                                     'das.ctime':header['das']['ctime'],
                                    },
                         '$set': {'das.expire':expire, 'das.status':status}},
                        safe=True)
            if  dasrecord:
                self.col.update({'_id':ObjectId(dasrecord['_id'])},
                     {'$set': {'das.expire':expire}}, safe=True)
        else:
            self.col.update({'qhash': dasquery.qhash,
                             'das.system':'das'},
                            {'$set': {'das.status': status}}, safe=True)

    def incache(self, dasquery, collection='merge', system=None):
        """
        Check if we have query results in cache, otherwise return null.
        Please note, input parameter query means MongoDB query, please
        consult MongoDB API for more details,
        http://api.mongodb.org/python/
        """
        self.remove_expired(collection)
        col  = self.mdb[collection]
        spec = {'qhash':dasquery.qhash}
        if  system:
            spec.update({'das.system': system})
        res  = col.find(spec=spec).count()
        msg  = "(%s, coll=%s) found %s results" % (dasquery, collection, res)
        self.logger.info(msg)
        if  res:
            return True
        return False

    def nresults(self, dasquery, collection='merge'):
        """Return number of results for given query."""
        if  dasquery.aggregators:
            return len(dasquery.aggregators)
        # Distinguish 2 use cases, unique filter and general query
        # in first one we should count only unique records, in later
        # we can rely on DB count() method. Pleas keep in mind that
        # usage of fields in find doesn't account for counting, since it
        # is a view over records found with spec, so we don't need to use it.
        col  = self.mdb[collection]
        fields, filter_cond = self.get_fields(dasquery)
        if  not fields:
            spec = dasquery.mongo_query.get('spec', {})
        else:
            spec = {'qhash':dasquery.qhash, 'das.empty_record':0}
        if  filter_cond:
            spec.update(filter_cond)
        if  dasquery.unique_filter:
            skeys = self.mongo_sort_keys(collection, dasquery)
            if  skeys:
                gen = col.find(spec=spec).sort(skeys)
            else:
                gen = col.find(spec=spec)
            res = len([r for r in unique_filter(gen)])
        else:
            res = col.find(spec=spec).count()
        msg = "%s" % res
        self.logger.info(msg)
        return res

    def mongo_sort_keys(self, collection, dasquery):
        """
        Find list of sort keys for a given DAS query. Check existing
        indexes and either use fields or spec keys to find them out.
        Return list of mongo sort keys in a form of (key, order).
        """
        # try to get sort keys all the time to get ordered list of
        # docs which allow unique_filter to apply afterwards
        fields = dasquery.mongo_query.get('fields')
        spec   = dasquery.mongo_query.get('spec')
        skeys  = dasquery.sortkeys
        mongo_skeys = []
        if  skeys:
            for key in skeys:
                if  key.find('-') != -1: # reverse order, e.g. desc
                    mongo_skeys.append((key.replace('-', ''), DESCENDING))
                else:
                    mongo_skeys.append((key, ASCENDING))
        else:
            existing_idx = [i for i in self.existing_indexes(collection)]
            if  fields:
                lkeys = []
                for key in fields:
                    for mkey in self.mapping.mapkeys(key):
                        if  mkey not in lkeys:
                            lkeys.append(mkey)
            else:
                lkeys = spec.keys()
            keys = [k for k in lkeys \
                if k.find('das') == -1 and k.find('_id') == -1 and \
                        k in existing_idx]
            mongo_skeys = [(k, ASCENDING) for k in keys]
        return mongo_skeys

    def existing_indexes(self, collection='merge'):
        """
        Get list of existing indexes in DB. They are returned by index_information
        API in the following for:

        .. doctest::

            {u'_id_': {u'key': [(u'_id', 1)], u'v': 0},
             u'das.expire_1': {u'key': [(u'das.expire', 1)], u'v': 0},
             ...
             u'tier.name_-1': {u'key': [(u'tier.name', -1)], u'v': 0}}
        """
        col = self.mdb[collection]
        for val in col.index_information().values():
            for idx in val['key']:
                yield idx[0] # index name

    def get_records(self, col, spec, fields, skeys, idx, limit, unique=False):
        "Generator to get records from MongoDB. It correctly applies"
        if  fields:
            for key in fields: # ensure that fields keys will be presented
                if  key not in self.das_internal_keys and \
                    not spec.has_key(key):
                    spec.update({key: {'$exists':True}})
        try:
            res = col.find(spec=spec, fields=fields)
            if  skeys:
                res = res.sort(skeys)
            if  not unique:
                if  idx:
                    res = res.skip(idx)
                if  limit:
                    res = res.limit(limit)
        except Exception as exp:
            print_exc(exp)
            row = {'exception': str(exp)}
            res = []
            yield row
        if  unique:
            if  limit:
                gen = itertools.islice(unique_filter(res), idx, idx+limit)
            else:
                gen = unique_filter(res)
            for row in gen:
                yield row
        else:
            for row in res:
                yield row

    def get_from_cache(self, dasquery, idx=0, limit=0, collection='merge'):
        "Generator which retrieves results from the cache"
        if  dasquery.service_apis_map(): # valid DAS query
            result = self.get_das_records(dasquery, idx, limit, collection)
        else: # pure MongoDB query
            coll    = self.mdb[collection]
            fields  = dasquery.mongo_query.get('fields', None)
            spec    = dasquery.mongo_query.get('spec', {})
            if  dasquery.filters:
                if  fields == None:
                    fields = dasquery.filters
                else:
                    fields += dasquery.filters
            skeys   = self.mongo_sort_keys(collection, dasquery)
            result  = self.get_records(coll, spec, fields, skeys, \
                            idx, limit, dasquery.unique_filter)
        for row in result:
            yield row

    def get_das_records(self, dasquery, idx=0, limit=0, collection='merge'):
        "Generator which retrieves DAS records from the cache"
        col = self.mdb[collection]
        msg = "(%s, %s, %s, coll=%s)" % (dasquery, idx, limit, collection)
        self.logger.info(msg)

        idx = int(idx)
        fields, filter_cond = self.get_fields(dasquery)
        if  not fields:
            spec = dasquery.mongo_query.get('spec', {})
        else:
            spec = {'qhash':dasquery.qhash, 'das.empty_record':0}
        if  filter_cond:
            spec.update(filter_cond)
        if  fields: # be sure to extract das internal keys
            fields += self.das_internal_keys
        # try to get sort keys all the time to get ordered list of
        # docs which allow unique_filter to apply afterwards
        skeys   = self.mongo_sort_keys(collection, dasquery)
        res     = self.get_records(col, spec, fields, skeys, \
                        idx, limit, dasquery.unique_filter)
        counter = 0
        for row in res:
            counter += 1
            yield row

        if  counter:
            msg = "yield %s record(s)" % counter
            self.logger.info(msg)

        # if no raw records were yield we look-up possible error records
        if  not counter:
            nrec = self.col.find({'qhash':dasquery.qhash}).count()
            if  nrec:
                msg = "for query %s, found %s non-result record(s)" \
                        % (dasquery, nrec)
                prf = 'DAS WARNING, monogocache:get_from_cache '
                print dastimestamp(prf), msg

    def map_reduce(self, mr_input, dasquery, collection='merge'):
        """
        Wrapper around _map_reduce to allow sequential map/reduce
        operations, e.g. map/reduce out of map/reduce. 

        mr_input is either alias name or list of alias names for
        map/reduce functions.

        Input dasquery which is applied to first
        iteration of map/reduce functions.
        """
        # NOTE: I need to revisit mapreduce.
        spec = dasquery.mongo_query['spec']
        if  not isinstance(mr_input, list):
            mrlist = [mr_input]
        else:
            mrlist = mr_input
        coll = self.mdb[collection]
        for mapreduce in mrlist:
            if  mapreduce == mrlist[0]:
                cond = spec
            else:
                cond = None
            coll = self._map_reduce(coll, mapreduce, cond)
        for row in coll.find():
            yield row

    def _map_reduce(self, coll, mapreduce, spec=None):
        """
        Perform map/reduce operation over DAS cache using provided
        collection, mapreduce name and optional conditions.
        """
        self.logger.debug("(%s, %s)" % (mapreduce, spec))
        record = self.mrcol.find_one({'name':mapreduce})
        if  not record:
            raise Exception("Map/reduce function '%s' not found" % mapreduce)
        fmap = record['map']
        freduce = record['reduce']
        if  spec:
            result = coll.map_reduce(Code(fmap), Code(freduce), query=spec)
        else:
            result = coll.map_reduce(Code(fmap), Code(freduce))
        msg = "found %s records in %s" % (result.count(), result.name)
        self.logger.info(msg)
        self.logger.debug(fmap)
        self.logger.debug(freduce)
        return result

    def get_map_reduce(self, name=None):
        """
        Return definition of map/reduce functions for provided name
        or gives full list.
        """
        spec = {}
        if  name:
            spec = {'name':name}
        result = self.mrcol.find(spec)
        for row in result:
            yield row

    def merge_records(self, dasquery):
        """
        Merge DAS records for provided query. We perform the following
        steps:
        1. get all queries from das.cache by ordering them by primary key
        2. run aggregtor function to merge neighbors
        3. insert records into das.merge
        """
        self.logger.debug(dasquery)
        id_list = []
        expire  = 9999999999 # future
        # get all API records for given DAS query
        spec    = {'qhash':dasquery.qhash, 'query':{'$exists':True}}
        records = self.col.find(spec)
        for row in records:
            # find smallest expire timestamp to be used by aggregator
            if  row['das']['expire'] < expire:
                expire = row['das']['expire']
            if  row['_id'] not in id_list:
                id_list.append(row['_id'])
        inserted = 0
        lookup_keys = set()
        fields = dasquery.mongo_query.get('fields')
        if  not fields: # Mongo
            fields = []
        for key in fields:
            for pkey in self.mapping.mapkeys(key):
                lookup_keys.add(pkey)
        for pkey in lookup_keys:
            skey = [(pkey, DESCENDING)]
            # lookup all service records
            spec = {'das_id': {'$in': id_list}, 'das.primary_key': pkey}
            if  self.verbose:
                nrec = self.col.find(spec).sort(skey).count()
                msg  = "merging %s records, for %s key" % (nrec, pkey) 
            else:
                msg  = "merging records, for %s key" % pkey
            self.logger.debug(msg)
            records = self.col.find(spec).sort(skey)
            # aggregate all records
            agen = aggregator(dasquery, records, expire)
            # diff aggregated records
            gen  = das_diff(agen, self.mapping.diff_keys(pkey.split('.')[0]))
            # insert all records into das.merge using bulk insert
            size = self.cache_size
            try:
                while True:
                    nres = self.merge.insert(\
                        itertools.islice(gen, size), safe=True)
                    if  nres and isinstance(nres, list):
                        inserted += len(nres)
                    else:
                        break
            except InvalidDocument as exp:
                msg = "Caught bson error: " + str(exp)
                self.logger.info(msg)
                records = self.col.find(spec).sort(skey)
                gen = aggregator(dasquery, records, expire)
                genrows = parse2gridfs(self.gfs, pkey, gen, self.logger)
                das_dict = {'das':{'expire':expire, 'empty_record': 0,
                        'primary_key':[k for k in lookup_keys],
                        'system': ['gridfs']}, 'qhash':dasquery.qhash,
                        'cache_id':[], 'das_id': id_list}
                for row in genrows:
                    row.update(das_dict)
                    self.merge.insert(row, safe=True)
            except InvalidOperation:
                pass
        if  inserted:
            self.logdb.insert('merge', {'insert': inserted})
        elif  not lookup_keys: # we get query w/o fields
            pass
        else: # we didn't merge anything, it is DB look-up failure
            empty_expire = time.time() + 20 # secs, short enough to expire
            empty_record = {'das':{'expire':empty_expire,
                                   'primary_key':list(lookup_keys),
                                   'empty_record': 1},
                            'cache_id':[], 'das_id': id_list}
            for key, val in dasquery.mongo_query['spec'].iteritems():
                if  key.find('.') == -1:
                    empty_record[key] = []
                else: # it is compound key, e.g. site.name
                    newkey, newval = convert_dot_notation(key, val)
                    empty_record[newkey] = adjust_mongo_keyvalue(newval)
            self.merge.insert(empty_record, safe=True)
            # update DAS records (both meta and data ones, by using qhash)
            nval = {'$set': {'das.expire':empty_expire}}
            spec = {'qhash':dasquery.qhash}
            self.col.update(spec, nval, multi=True, safe=True)

    def update_cache(self, dasquery, results, header):
        """
        Insert results into cache. Use bulk insert controller by
        self.cache_size. Upon completion ensure indexies.
        """
        # insert/check query record in DAS cache
        self.insert_query_record(dasquery, header)

        # update results records in DAS cache
        gen  = self.generate_records(dasquery, results, header)
        inserted = 0
        # bulk insert
        try:
            while True:
                nres = self.col.insert(\
                        itertools.islice(gen, self.cache_size), safe=True)
                if  nres and isinstance(nres, list):
                    inserted += len(nres)
                else:
                    break
        except InvalidOperation:
            pass
        if  inserted:
            self.logdb.insert('cache', {'insert': inserted})

    def insert_query_record(self, dasquery, header):
        """
        Insert query record into DAS cache.
        """
        dasheader  = header['das']
        # check presence of API record in a cache
        system     = dasheader['system']
        if  not self.incache(dasquery, collection='cache', system=system):
            msg = "query=%s, header=%s" % (dasquery, header)
            self.logger.debug(msg)
            q_record = dict(das=dasheader, query=dasquery.storage_query)
            q_record['das']['empty_record'] = 0
            q_record['das']['status'] = "requested"
            q_record['qhash'] = dasquery.qhash
            self.col.insert(q_record, safe=True)

    def generate_records(self, dasquery, results, header):
        """
        Iterate over provided results, update records and yield them
        to next level (update_cache)
        """
        self.logger.debug("(%s) store to cache" % dasquery)
        if  not results:
            return
        # update das record with new status
        status = 'Update DAS cache, %s API' % header['das']['api'][0]
        self.update_query_record(dasquery, status, header)

        dasheader  = header['das']
        expire     = dasheader['expire']
        system     = dasheader['system']
        rec        = [k for i in header['lookup_keys'] for k in i.values()]
        cond_keys  = dasquery.mongo_query['spec'].keys()
        # get API record id
        spec       = {'qhash':dasquery.qhash, 'das.system':system}
        record     = self.col.find_one(spec, fields=['_id'])
        counter    = 0
        prim_key   = rec[0][0]#use rec instead of lkeys[0] which re-order items
        if  record:
            objid  = record['_id']
            if  isinstance(results, list) or isinstance(results, GeneratorType):
                for item in results:
                    counter += 1
                    item['das'] = dict(expire=expire, primary_key=prim_key,
                                       condition_keys=cond_keys,
                                       instance=dasquery.instance,
                                       system=system, empty_record=0)
                    item['das_id'] = str(objid)
                    item['qhash'] = dasquery.qhash
                    yield item
            else:
                print "\n\n ### results = ", str(results)
                raise Exception('Provided results is not a list/generator type')
        self.logger.info("\n")
        msg = "%s yield %s rows" % (dasheader['system'], counter)
        self.logger.info(msg)

    def remove_from_cache(self, dasquery):
        """
        Remove query from DAS cache. To do so, we retrieve API record
        and remove all data records from das.cache and das.merge
        """
        records = self.col.find({'qhash':dasquery.qhash})
        id_list = []
        for row in records:
            if  row['_id'] not in id_list:
                id_list.append(row['_id'])
        spec = {'das_id':{'$in':id_list}}
        self.logdb.insert('merge', {'delete': self.col.find(spec).count()})
        self.merge.remove(spec)
        self.logdb.insert('cache', {'delete': self.col.find(spec).count()})
        self.col.remove(spec)
        self.col.remove({'qhash':dasquery.qhash})

    def clean_cache(self):
        """
        Clean expired docs in das.cache and das.merge. 
        """
        current_time = time.time()
        query = {'das.expire': { '$lt':current_time} }
        self.logdb.insert('merge', {'delete': self.merge.find(query).count()})
        self.merge.remove(query)
        self.logdb.insert('cache', {'delete': self.col.find(query).count()})
        self.col.remove(query)

    def delete_cache(self):
        """
        Delete all results in DAS cache/merge collection, including
        internal indexes.
        """
        self.logdb.insert('cache', {'delete': self.col.count()})
        self.col.remove({})
        try: 
            self.col.drop_indexes()
        except:
            pass
        self.logdb.insert('merge', {'delete': self.merge.count()})
        self.merge.remove({})
        try:
            self.merge.drop_indexes()
        except:
            pass
