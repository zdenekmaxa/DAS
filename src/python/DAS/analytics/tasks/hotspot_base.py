#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-
#pylint: disable-msg=W0702,W0703
"""
Base class for scheduling analyzers
"""
__author__ = "Gordon Ball"

import time
import collections
from DAS.utils.logger import PrintManager

class HotspotBase(object):
    """
    This is a base-class for periodically-running
    analyzers that want to examine the moving average
    of some key->counter map, and pick the top few
    for further attention.

    DASQueries are extracted from analytics DB. The selected items
    are passed to generate_task callback implemented in subclasses.
    It look-up DAS query expiration timestamp and if necessary
    calls DAS to get it (along with results of the query).
    """
    def __init__(self, **kwargs):
        self.logger = PrintManager('HotspotBase', kwargs.get('verbose', 0))
        self.das = kwargs['DAS']        
        self.fraction = float(kwargs.get('fraction', 0.15))
        self.mode = kwargs.get('mode','calls').lower()
        self.period = int(kwargs.get('period', 86400*30))
        self.interval = kwargs['interval']
        self.allowed_gap = int(kwargs.get('allowed_gap', 3600))
        self.identifier = kwargs['identifier']
        
    def __call__(self):
        """
        Perform a hotspot-like analysis. Subclasses shouldn't
        need to reimplement this method.

        We start with building selection chain. It consists of
        analytics summaries -> items -> preselected items ->
        mutable items. The final set of items is passed to
        task generation step (implemented in subclasses).
        The final report is generated and returned back.
        """
        
        epoch_end = time.time()
        epoch_start = epoch_end - self.period
        
        summaries = self.get_summaries(epoch_start, epoch_end)
        self.logger.info("Got %s summaries" % len(summaries))
        
        items = self.get_all_items(summaries)
        self.logger.info("Got %s items" % len(items))
        
        items = self.preselect_items(items)
        self.logger.info("Preselected to %s items" % len(items))
        
        items = self.select_items(items)
        self.logger.info("Selected %s items (%s:%s)" \
                         % (len(items), self.mode, self.fraction))
        
        items = self.mutate_items(items)
        self.logger.info("Mutated to %s items" % len(items))
        
        retval = {'mode': self.mode,
                  'fraction': self.fraction,
                  'epoch_start': epoch_start,
                  'epoch_end': epoch_end,
                  'summaries': len(summaries),
                  'selected': dict(items).items()}
        
        new_tasks = []
        failed_items = []
        for item, count in items.items():
            try:
                self.logger.info("Generating task for %s" % item)
                for task in \
                    self.generate_task(item, count, epoch_start, epoch_end):
                    new_tasks.append(task)
            except Exception as exc:
                failed_items.append((item, count, str(exc)))
        retval['new_tasks'] = new_tasks
        retval['failed_items'] = failed_items
        
        retval.update(self.report())
        
        return retval
    
    def generate_task(self, item, count, epoch_start, epoch_end):
        """
        For the given selected key, generate an appropriate task
        dictionary as understood by taskscheduler.
        
        Should be a generator or return an iterable
        """
        raise NotImplementedError
    
    def report(self):
        """
        Generate some extra keys to go in the job report, if desired.
        """
        return {}
    
    def preselect_items(self, items):
        """
        This is a part of selection chain.

        Optionally, preselect the items for consideration.
        A subclass wishing to exclude certain key types could
        do so here (but could also do so in make_one_summary).

        This is a good place to implement clustering algorithm
        for selected items. For example, if several queries are
        selected, we may analyze who has more weight and only
        pass those for task generation step.
        """
        return items
    
    def mutate_items(self, items):
        """
        This is a last part of selection chain.

        Optionally, mutate the selected items.
        A subclass wishing to merge together keys should
        do so here.
        """
        return items
    
    def get_all_items(self, summaries):
        """
        Merge the summary dictionaries.
        """
        items = collections.defaultdict(int)
        for summary in summaries:
            for key, val in summary.items():
                items[key] += val
        return items
    
    def select_items(self, items):
        """
        Take a mapping of item->count pairs and determine
        which are "hot" based on the selected mode.
        """
        sorted_keys = sorted(items.keys(), key=lambda x: items[x], reverse=True)
        selected_items = {}
        if self.mode == 'calls':
            total_calls = sum(items.values())
            running_total = 0
            for key in sorted_keys:
                running_total += items[key]
                selected_items[key] = items[key]
                if running_total > total_calls * self.fraction:
                    break
        elif self.mode == 'keys':
            selected_items = dict([(k, items[k]) 
               for k in sorted_keys[0:int(len(sorted_keys)*self.fraction)]])
        elif self.mode == 'fixed':
            selected_items = dict([(k, items[k]) 
               for k in sorted_keys[0:int(self.fraction)]])
        else:
            raise NotImplementedError
        return selected_items
    
    def get_summaries(self, epoch_start, epoch_end):
        """
        Fetch all the available pre-computed summaries
        and determine if any need to be constructed at this time.
        """
        #get all the summaries we can from this time
        try:
            summaries = self.das.analytics.get_summary(self.identifier, 
                                                       after=epoch_start,
                                                       before=epoch_end)
            self.logger.info("Found %s summary documents." % len(summaries)) 
        except:
            summaries = []
        #see how much coverage of the requested period we have
        summaries = sorted(summaries, key=lambda x: x['start'])
        extra_summaries = []
        last_time = epoch_start
        for summary in summaries:
            if last_time < summary['start']:
                result = self.make_summary(last_time, summary['start'])
                extra_summaries.extend(result)
            last_time = summary['finish']
        result = self.make_summary(last_time, epoch_end)
        extra_summaries.extend(result)
        summaries = [dict(s['keys']) for s in summaries]
        summaries += extra_summaries
        
        return summaries
    
    def make_summary(self, start, finish):
        """
        Split the summarise requests into interval-sized chunks and decide
        if they're necessary at all.
        """
        self.logger.info("Found summary gap: %s->%s (%s)" \
                         % (start, finish, finish-start))
        result = []
        delta = finish - start
        if delta > self.allowed_gap:
            if delta > self.interval:
                blocks = int(delta/self.interval)
                span = delta/blocks
                self.logger.info("Gap longer than interval, " +\
                                 "creating %s summaries." % blocks)
                for i in range(blocks):
                    try:
                        summary = self.make_one_summary(start+span*i, 
                                                        start+span*(i+1))
                        self.das.analytics.add_summary(self.identifier,
                                               start+span*i,
                                               start+span*(i+1),
                                               keys=(dict(summary)).items())
                        result.append(summary)
                    except:
                        pass
                    
            else:
                try:
                    summary = self.make_one_summary(start, finish)
                    self.das.analytics.add_summary(self.identifier,
                                                   start,
                                                   finish,
                                                   keys=(dict(summary)).items())
                    result.append(summary)
                except:
                    pass
        else:
            self.logger.info("...short enough to ignore.")
            
        return result
    
    def make_one_summary(self, start, finish):
        """
        Actually make a summary of item->count pairs
        for the specified time range. Subclasses need to
        implement this for the analysis in question.
        """
        raise NotImplementedError
