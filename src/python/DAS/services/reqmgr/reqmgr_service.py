#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-

"""
ReqMgr service
"""
__author__ = "Valentin Kuznetsov"

from DAS.services.abstract_service import DASAbstractService
from DAS.utils.utils import map_validator
from DAS.utils.url_utils import getdata

class ReqMgrService(DASAbstractService):
    """
    Helper class to provide DBS service
    """
    def __init__(self, config):
        DASAbstractService.__init__(self, 'reqmgr', config)
        self.map = self.dasmapping.servicemap(self.name)
        map_validator(self.map)

    def getdata(self, url, params, expire, headers=None, post=None):
        """URL call wrapper"""
        if  url[-1] == '/':
            url = url[:-1]
        for key, _val in params.iteritems():
            url = '/'.join([url, params[key]])
        params = {}
        return getdata(url, params, headers, expire, post,
                self.error_expire, self.verbose, self.ckey, self.cert,
                system=self.name)

    def parser(self, query, dformat, source, api):
        """
        ReqMgr data-service parser.
        """
        if  api == 'inputdataset':
            gen = DASAbstractService.parser(self, query, dformat, source, api)
            for row in gen:
                try:
                    data = row['dataset']
                    data = \
                    data['WMCore.RequestManager.DataStructs.Request.Request']
                    yield data
                except:
                    yield row
