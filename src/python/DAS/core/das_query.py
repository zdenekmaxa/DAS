#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-
"""
File: das_query.py
Author: Gordon Ball and Valentin Kuznetsov
Description: Main class to hold DAS query object
"""

# system modules
import re
import copy
from   pymongo.objectid import ObjectId

# DAS modules
import DAS.utils.jsonwrapper as json
from   DAS.utils.utils import genkey, deepcopy, print_exc
from   DAS.utils.query_utils import compare_specs
from   DAS.core.das_parser import ql_manager

class DASQuery(object):
    """
    Wrapper around base query. Uses properties to calculate
    qhash, storage query, mongo query on demand. Other methods, 
    such as to_bare_query return a new DASQuery, modified
    appropriately.
    """
    def __init__(self, query, **flags):
        """
        Accepts general form of DAS query, supported formats are
        DAS input query, DAS mongo query, DAS storage query. The
        supplied flags can carry any query attributes, e.g.
        filters, aggregators, system, instance, etc.
        """
        self._mongoparser   = None
        self._params        = {}
        self._service_apis_map = {}
        self._str           = ''
        self._query         = ''
        self._storage_query = {}
        self._mongo_query   = {}
        self._qhash         = None
        self._system        = None
        self._instance      = None
        self._loose_query   = None
        self._pattern_query = None
        self._sortkeys      = []
        self._filters       = {}
        self._mapreduce     = []
        self._aggregators   = []
        self._flags         = flags

        # loop over flags and set available attributes
        for key, val in flags.iteritems():
            setattr(self, '_%s' % key, val)

        # test data type of input query and apply appropriate initialization
        if  isinstance(query, basestring):
            self._query = query
            try:
                self._mongo_query = self.mongoparser.parse(query)
                for key, val in flags.iteritems():
                    if  key in ['mongoparser']:
                        continue
                    if  not self._mongo_query.has_key(key):
                        self._mongo_query[key] = val
            except Exception as exp:
                msg = "Fail to parse DAS query='%s'" % query
                print_exc(msg, print_traceback=False)
                raise exp
        elif isinstance(query, dict):
            newquery = {}
            for key, val in query.iteritems():
                newquery[key] = val
            if  isinstance(newquery.get('spec'), dict): # mongo query
                self._mongo_query = newquery
            else: # storage query
                self._storage_query = newquery
        elif isinstance(query, object) and hasattr(query, '__class__')\
            and query.__class__.__name__ == 'DASQuery':
            self._query = query.query
            self._mongo_query = query.mongo_query
            self._storage_query = query.storage_query
        else:
            raise Exception('Unsupport data type of DAS query')
        self.update_attr()

    def update_attr(self):
        """
        setup DAS query attributes if they were supplied in input query
        for instance if input query is mongo query/storage_query
        """
        self._instance    = self.mongo_query.get('instance', self._instance)
        self._system      = self.mongo_query.get('system', self._system)
        self._filters     = self.mongo_query.get('filters', self._filters)
        self._aggregators = \
                self.mongo_query.get('aggregators', self._aggregators)
        self._mapreduce   = self.mongo_query.get('mapreduce', self._mapreduce)

    ### Class properties ###

    @property
    def mongoparser(self):
        "mongoparser property of the DAS query"
        if  not self._mongoparser:
            self._mongoparser = ql_manager()
        return self._mongoparser

    @property
    def filters(self):
        "filters property of the DAS query"
        filters = self._mongo_query.get('filters', {})
        return filters.get('grep', [])

    @property
    def sortkeys(self):
        "sortkeys property of the DAS query"
        filters = self._mongo_query.get('filters', {})
        return filters.get('sort', [])

    @property
    def unique_filter(self):
        "Check if DAS query has unique filter"
        filters = self._mongo_query.get('filters', {})
        return True if 'unique' in filters.keys() else False

    @property
    def mapreduce(self):
        "mapreduce property of the DAS query"
        return self._mapreduce

    @property
    def aggregators(self):
        "aggregators property of the DAS query"
        return self._aggregators

    @property
    def system(self):
        "system property of the DAS query"
        return self._system

    @property
    def instance(self):
        "instance property of the DAS query"
        return self._instance

    @property
    def query(self):
        "query property of the DAS query (human readble form)"
        if  not self._query:
            fields = self.mongo_query.get('fields', [])
            if  not fields:
                fields = [] # will use empty list for conversion
            query  = ' '.join(fields)
            query += ' ' # space between fields and spec values
            query += ' '.join(['%s=%s' % (k, v) for k, v \
                        in self.mongo_query.get('spec', {}).iteritems()])
            self._query = query.strip()
        return self._query

    @property
    def storage_query(self):
        """
        Read only storage query, generated on demand.
        """
        if  not self._storage_query:
            self._storage_query = deepcopy(self.mongo_query)
            speclist = []
            for key, val in self._storage_query.pop('spec').iteritems():
                if  str(type(val)) == "<type '_sre.SRE_Pattern'>":
                    val = json.dumps(val.pattern)
                    speclist.append({"key":key, "value":val, "pattern":1})
                elif isinstance(val, ObjectId):
                    speclist.append({"key":key, "value":str(val)})
                else:
                    val = json.dumps(val)
                    speclist.append({"key":key, "value":val})
            self._storage_query['spec'] = speclist
        return self._storage_query
        
    @property
    def mongo_query(self):
        """
        Read only mongo query, generated on demand.
        """
        system = self._mongo_query.get('system', [])
        filters = self._mongo_query.get('filters', {})
        aggregators = self._mongo_query.get('aggregators', [])
        if  not self._mongo_query:
            self._mongo_query = deepcopy(self.storage_query)
            for key, val in self._mongo_query.iteritems():
                if  key not in ['fields', 'spec']:
                    setattr(self, '_%s' % key, val)
            spec = {}
            for item in self._mongo_query.pop('spec'):
                val = json.loads(item['value'])
                if  item.has_key('pattern'):
                    val = re.compile(val)
                spec.update({item['key'] : val})
            self._mongo_query['spec'] = spec
        # special case when user asks for all records
        fields = self._mongo_query.get('fields', None)
        if  fields and fields == ['records']:
            self._mongo_query['fields'] = None
            spec = {}
            for key, val in self._mongo_query['spec'].iteritems():
                if  key != 'records':
                    spec[key] = val
            self._mongo_query = dict(fields=None, spec=spec)
        if  filters:
            self._mongo_query.update({'filters':filters})
        if  aggregators:
            self._mongo_query.update({'aggregators':aggregators})
        if  system:
            self._mongo_query.update({'system':system})
        return self._mongo_query
    
    @property
    def qhash(self):
        """
        Read only qhash, generated on demand.
        """
        if  not self._qhash:
            sdict = deepcopy(self.storage_query)
            for key in ['filters', 'aggregators', 'mapreduce']:
                if  sdict.has_key(key):
                    del sdict[key]
            self._qhash = genkey(sdict)
        return self._qhash

    @property
    def loose_query(self):
        """
        Construct loose version of the query. That means add 
        pattern '*' to string type values for all conditions.
        """
        if  not self._loose_query:
            query   = deepcopy(self.mongo_query)
            spec    = query.get('spec', {})
            fields  = query.get('fields', None)
            newspec = {}
            for key, val in spec.iteritems():
                if  key != '_id' and \
                isinstance(val, str) or isinstance(val, unicode):
                    if  val[-1] != '*':
                        val += '*' # add pattern
                newspec[key] = val
            self._loose_query = dict(spec=newspec, fields=fields)
        return self._loose_query

    @property
    def pattern_query(self):
        """
        Patter property for DAS query whose spec is modified
        to regexes and $exists keys
        """
        if  not self._pattern_query:
            nmq = deepcopy(self.loose_query)
            
            def edit_dict(old):
                """
                Inner recursive dictionary manipulator
                """
                result = {}
                for key, val in old.iteritems():
                    if isinstance(val, basestring):
                        if  '*' in val:
                            if len(val) == 1:
                                result[key] = {'$exists': True}
                            else:
                                result[key] = \
                                    re.compile('^%s' % val.replace('*', '.*'))
                    elif isinstance(val, dict):
                        result[key] = edit_dict(val)
                    else:
                        result[key] = val
                return result
            
            nmq['spec'] = edit_dict(nmq['spec'])    
            self._pattern_query = nmq
        return self._pattern_query
    
    ### Class method ###

    def add_to_analytics(self):
        "Add DAS query to analytics DB"
        if  self.mongoparser:
            self.mongoparser.add_to_analytics(self.query, self.mongo_query)

    def params(self):
        "Extract params (keys, conditions and services) from mongo query"
        if  self._params:
            return self._params
        if  self.mongoparser:
            self._params = self.mongoparser.params(self.mongo_query)
        return self._params

    def service_apis_map(self):
        "Return data service APIs map who may answer DAS query"
        if  self._service_apis_map:
            return self._service_apis_map
        if  self.mongoparser:
            self._service_apis_map = \
                self.mongoparser.service_apis_map(self.mongo_query)
        return self._service_apis_map

    def is_bare_query(self):
        """
        Return true if we only have 'fields' and 'spec' keys.
        """
        return sorted(self.mongo_query.keys()) == ['fields', 'spec']
            
    def to_bare_query(self):
        """
        Return a new query containing only field and spec keys of this query.
        May be identical if this is already a bare query.
        """
        if  self.is_bare_query():
            return self
        mongo_query = {'fields': copy.deepcopy(self.mongo_query['fields']),
                'spec': deepcopy(self.mongo_query['spec'])}
        return mongo_query

    def to_dict(self):
        "Convert DAS query into dictionary"
        obj = dict(query=self.query, mongo_query=self.mongo_query,
                   instance=self.instance, filters=self.filters,
                   aggregators=self.aggregators, system=self.system,
                   qhash=self.qhash, mapreduce=self.mapreduce)
        return obj

    def has_id(self):
        """
        Check if there is an _id key in the spec.
        """
        return '_id' in self.mongo_query['spec']
    
    def has_mongo_id(self):
        """
        Check if the _id key is a mongo ObjectId
        """
        return isinstance(self.mongo_query.get('_id', None), ObjectId)
    
    def to_mongo_id(self):
        """
        Return a new DASQuery where the _id has been converted
        (as adjust_id) to a mongo ObjectId
        """
        nmq = deepcopy(self.mongo_query)
        if self.has_id():
            val = self.mongo_query['spec']['_id']
            if isinstance(val, str):
                nmq['spec']['_id'] = ObjectId(val)
            elif isinstance(val, unicode):
                nmq['spec']['_id'] = ObjectId(unicode.encode(val))
            elif isinstance(val, list):
                result = []
                for item in val:
                    if isinstance(val, str):
                        result.append(ObjectId(item))
                    elif isinstance(val, unicode):
                        result.append(ObjectId(unicode.encode(item)))
                    else:
                        raise Exception("non str|unicode _id.child")
                nmq['spec']['_id'] = result
            else:
                raise Exception("non str|unicode|list _id")
        return DASQuery(nmq, **self._flags)
    
    def flag(self, name):
        """
        Test the state of any flags that were set.
        """
        return self._flags.get(name, False)
    
    def is_superset_of(self, other):
        """
        Return true if we are a superset of other
        """
        return compare_specs(other.mongo_query, self.mongo_query)
    
    def is_subset_of(self, other):
        """
        Return true if we are not a superset of the other.
        This is perhaps not the same thing as "is subset of"
        """
        return compare_specs(self.mongo_query, other.mongo_query)
    
    def __gt__(self, other):
        "Query comparision operator"
        return self.is_superset_of(other)
    
    def __lt__(self, other):
        "Query comparision operator"
        return self.is_subset_of(other)
    
    def __eq__(self, other):
        "Query comparision operator"
        return self.qhash == other.qhash
    
    def __str__(self):
        "Query string representation"
        if  self._str:
            return self._str
        msg = """<query='''%s''' instance=%s qhash=%s>""" \
            % (self.query, self.instance, self.qhash)
        self._str = msg
        return msg
