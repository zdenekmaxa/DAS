#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-

"""
Config utilities
"""

__revision__ = "$Id: das_config.py,v 1.5 2009/04/07 20:10:04 valya Exp $"
__version__ = "$Revision: 1.5 $"
__author__ = "Valentin Kuznetsov"

import os
import ConfigParser

def das_configfile():
    """
    Return DAS configuration file name $DAS_ROOT/etc/das.cfg
    """
    if  os.environ.has_key('DAS_ROOT'):
        dasconfig = os.path.join(os.environ['DAS_ROOT'], 'etc/das.cfg')
        if  not os.path.isfile(dasconfig):
            raise EnvironmentError('No DAS config file %s found' % dasconfig)
        return dasconfig
    else:
        raise EnvironmentError('DAS_ROOT environment is not set up')

def das_readconfig(dasconfig=None):
    """
    Read DAS configuration file and store DAS parameters into returning
    dictionary.
    """
    if  not dasconfig:
        dasconfig = das_configfile()
    config = ConfigParser.ConfigParser()
    config.read(dasconfig)
    configdict = {}

    configdict['cache_servers'] = config.get('cache', 'servers', '')
    configdict['cache_lifetime'] = config.getint('cache', 'lifetime')
    configdict['couch_servers'] = config.get('couch', 'servers', '')
    configdict['couch_lifetime'] = config.getint('couch', 'lifetime')
    configdict['couch_cleantime'] = config.getint('couch', 'cleantime')

#    systems = config.get('das', 'systems', 'dbs,sitedb,phedex').split(',')
    systems = config.get('das', 'systems', 
                'dbs,sitedb,phedex,monitor,lumidb').split(',')
    verbose = config.getint('das', 'verbose')
    configdict['systems'] = systems
    configdict['verbose'] = verbose
    for system in systems:
        verbose = config.getint(system, 'verbose')
        expire  = config.getint(system, 'expire')
        url     = config.get(system, 'url', '')
        configdict[system] = {'verbose': verbose, 'expire': expire,
                              'url'  : url}
    mapping = {}
    for item in  config.options('mapping'):
        services = item.split(',')
        keys = config.get('mapping', item).split(',')
        mapping[(services[0], services[1])] = keys
    configdict['mapping'] = mapping
    return configdict

def das_writeconfig():
    """
    Write DAS configuration file
    """

    config = ConfigParser.ConfigParser()

    systems = 'dbs,sitedb,phedex,monitor,lumidb'
    config.add_section('das')
    config.set('das', 'systems', '%s' % systems)
    config.set('das', 'verbose', 1)

    config.add_section('cache')
    config.set('cache', 'servers', '127.0.0.1:11211' )
    config.set('cache', 'lifetime', 60) # in seconds

    config.add_section('couch')
    config.set('couch', 'servers', 'http://localhost:5984' )
    config.set('couch', 'lifetime', 1*24*60*60) # in seconds
    config.set('couch', 'cleantime', 2*60*60) # in seconds

    config.add_section('dbs')
    config.set('dbs', 'expire', 600) # in seconds
    config.set('dbs', 'verbose', 1)
    config.set('dbs', 'url', 
    'http://cmsdbsprod.cern.ch/cms_dbs_prod_global/servlet/DBSServlet')

    config.add_section('sitedb')
    config.set('sitedb', 'expire', 600)
    config.set('sitedb', 'verbose', 1)
    config.set('sitedb', 'url', 
    'https://cmsweb.cern.ch/sitedb/json/index')

    config.add_section('phedex')
    config.set('phedex', 'expire', 600)
    config.set('phedex', 'verbose', 1)
    config.set('phedex', 'url', 
    'https://cmsweb.cern.ch/phedex/datasvc/json/prod')

    config.add_section('monitor')
    config.set('monitor', 'expire', 600)
    config.set('monitor', 'verbose', 1)
    config.set('monitor', 'url', 
    'https://cmsweb.cern.ch/overview/')

    config.add_section('lumidb')
    config.set('lumidb', 'expire', 600)
    config.set('lumidb', 'verbose', 1)
    config.set('lumidb', 'url', 
    'http://cmslumi.cern.ch/lumi/servlet/LumiServlet')

#        config.add_section('runsum')
#        config.set('runsum', 'verbose', 1)
#        config.set('runsum', 'url', '')

#        maps = {'dbs,sitedb':'site', 'dbs,phedex':'block,site', 
#                'dbs,runsum':'run', 'phedex,sitedb':'site'}
    maps = {'dbs,sitedb':'site', 'dbs,phedex':'block,site', 
            'phedex,sitedb':'site', 'monitor,sitedb':'site',
            'dbs,lumidb':'lumi,run'}
    config.add_section('mapping')
    for key, val in maps.items():
        config.set('mapping', '%s' % key, '%s' % val)

    dasconfig = das_configfile()
    config.write(open(dasconfig, 'wb'))
    return dasconfig