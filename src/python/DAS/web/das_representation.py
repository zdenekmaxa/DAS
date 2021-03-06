#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-
#pylint: disable-msg=W0702,R0912,R0914,R0904,R0201
"""
File: das_representation.py
Author: Valentin Kuznetsov <vkuznet@gmail.com>
Description: Abstract interface to represent DAS records
"""

# system modules
import urllib

# DAS modules
from DAS.utils.ddict import DotDict
from DAS.utils.das_config import das_readconfig
from DAS.utils.utils import getarg, deepcopy
from DAS.web.das_webmanager import DASWebManager
from DAS.web.tools import exposedasjson, exposetext, exposedasplist
from DAS.web.utils import quote, das_json

class DASRepresentation(DASWebManager):
    """
    DASRepresentation is an abstract class which represents DAS records
    """
    def __init__(self, config):
        DASWebManager.__init__(self, config)
        self.base       = config['web_server'].get('url_base', 'das')
        self.dasconfig  = das_readconfig()

    def listview(self, head, data):
        """
        Represent data in list view.
        """
        kwargs  = head.get('args')
        total   = head.get('nresults', 0)
        incache = head.get('incache')
        main    = self.pagination(total, incache, kwargs)
        style   = 'white'
        page    = ''
        pad     = ''
        for row in data:
            if  not row:
                continue
            if  style == 'white':
                style = 'gray'
            else:
                style = 'white'
            try:
                mongo_id = row['_id']
            except Exception as exc:
                msg  = str(exc)
                msg += '\nFail to process row\n%s' % str(row)
                raise Exception(msg)
            page += '<div class="%s"><hr class="line" />' % style
            jsonhtml = das_json(row, pad)
            if  row.has_key('das') and row['das'].has_key('conflict'):
                conflict = ', '.join(row['das']['conflict'])
            else:
                conflict = ''
            page += self.templatepage('das_row', systems='', \
                    sanitized_data=jsonhtml, id=mongo_id, rec_id=mongo_id,
                    conflict=conflict)
            page += '</div>'
        main += page
        main += '<div align="right">DAS cache server time: %5.3f sec</div>' \
                % head['ctime']
        return main

    def tableview(self, head, data):
        """
        Represent data in tabular view.
        """
        kwargs   = head.get('args')
        total    = head.get('nresults', 0)
        dasquery = kwargs['dasquery']
        filters  = dasquery.filters
        titles   = []
        incache  = head.get('incache')
        page     = self.pagination(total, incache, kwargs)
        if  filters:
            for flt in filters:
                if  flt.find('=') != -1 or flt.find('>') != -1 or \
                    flt.find('<') != -1:
                    continue
                titles.append(flt)
        style  = 1
        tpage  = ""
        pkey   = None
        for row in data:
            rec  = []
            if  not pkey and row.has_key('das') and \
                row['das'].has_key('primary_key'):
                pkey = row['das']['primary_key'].split('.')[0]
            if  dasquery.filters:
                for flt in dasquery.filters:
                    rec.append(DotDict(row).get(flt))
            else:
                titles = []
                for key, val in row.iteritems():
                    skip = 0
                    if  not filters:
                        if  key in titles:
                            skip = 1
                        else:
                            titles.append(key)
                    if  not skip:
                        rec.append(val)
            if  style:
                style = 0
            else:
                style = 1
            link = '<a href="/das/records/%s?collection=merge">link</a>' \
                        % quote(str(row['_id'])) # cgi.escape the id
            tpage += self.templatepage('das_table_row', rec=rec, tag='td', \
                        style=style, encode=1, record=link)
        theads = list(titles) + ['Record']
        thead = self.templatepage('das_table_row', rec=theads, tag='th', \
                        style=0, encode=0, record=0)
        page += '<br />'
        page += '<table class="das_table">' + thead + tpage + '</table>'
        page += '<br />'
        page += '<div align="right">DAS cache server time: %5.3f sec</div>' \
                % head['ctime']
        return page

    def pagination(self, total, incache, kwds):
        """
        Construct pagination part of the page. It accepts total as a
        total number of result as well as dict of kwargs which
        contains idx/limit/query/input parameters, as well as other
        parameters used in URL by end-user.
        """
        kwargs  = deepcopy(kwds)
        if  kwargs.has_key('dasquery'):
            del kwargs['dasquery'] # we don't need it
        idx     = getarg(kwargs, 'idx', 0)
        limit   = getarg(kwargs, 'limit', 10)
        uinput  = getarg(kwargs, 'input', '')
        page    = ''
        if  total > 0:
            params = {} # will keep everything except idx/limit
            for key, val in kwargs.iteritems():
                if  key != 'idx' and key != 'limit' and key != 'query':
                    params[key] = val
            url   = "%s/request?%s" \
                    % (self.base, urllib.urlencode(params, doseq=True))
            page += self.templatepage('das_pagination', \
                nrows=total, idx=idx, limit=limit, url=url)
        else:
            page = self.templatepage('das_noresults', query=uinput,
                        incache=incache)
        return page

    @exposetext
    def plainview(self, head, data):
        """
        Represent data in DAS plain view for queries with filters.
        """
        dasquery = head['dasquery']
        fields   = dasquery.mongo_query.get('fields', [])
        filters  = dasquery.filters
        results = ""
        for row in data:
            if  filters:
                for flt in filters:
                    if  flt.find('=') != -1 or flt.find('>') != -1 or \
                        flt.find('<') != -1:
                        continue
                    try:
                        for obj in DotDict(row).get_values(flt):
                            results += str(obj) + '\n'
                    except:
                        pass
                results += '\n'
            else:
                for item in fields:
                    try:
                        mapkey = '%s.name' % item
                        key, att = mapkey.split('.')
                        if  row.has_key(key):
                            val = row[key]
                            if  isinstance(val, dict):
                                results += val.get(att, '')
                            elif isinstance(val, list):
                                for item in val:
                                    results += item.get(att, '')
                                    results += '\n'
                    except:
                        pass
                results += '\n'
        return results

    @exposedasplist
    def xmlview(self, head, data):
        "Represent data in XML data format"
        try: # remove DASQuery object from the head before serialization
            del head['dasquery']
        except:
            pass
        result = dict(head)
        result['data'] = [r for r in data]
        return result

    @exposedasjson
    def jsonview(self, head, data):
        "Represent data in JSON data format"
        try: # remove DASQuery object from the head before serialization
            del head['dasquery']
        except:
            pass
        result = dict(head)
        result['data'] = [r for r in data]
        return result
