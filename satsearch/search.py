import json
import os
import logging
import requests

import os.path as op
import satsearch.config as config

from satstac import Collection, Item, Items
from satstac.utils import dict_merge


logger = logging.getLogger(__name__)


class SatSearchError(Exception):
    pass


class Search(object):
    """ One search query (possibly multiple pages) """

    def __init__(self, **kwargs):
        """ Initialize a Search object with parameters """
        self.kwargs = kwargs
        for k in self.kwargs:
            if k == 'datetime':
                self.kwargs['time'] = self.kwargs['datetime']
                del self.kwargs['datetime']

    @classmethod
    def search(cls, **kwargs):
        if 'collection' in kwargs:
            q = 'collection=%s' % kwargs['collection']
            if 'property' not in kwargs:
                kwargs['property'] = []
            kwargs['property'].append(q)
            del kwargs['collection']
        symbols = {'=': 'eq', '>': 'gt', '<': 'lt', '>=': 'gte', '<=': 'lte'}
        if 'property' in kwargs and isinstance(kwargs['property'], list):
            queries = {}
            for prop in kwargs['property']:
                for s in symbols:
                    parts = prop.split(s)
                    if len(parts) == 2:
                        queries = dict_merge(queries, {parts[0]: {symbols[s]: parts[1]}})
                        break
            del kwargs['property']
            kwargs['query'] = queries
        directions = {'>': 'desc', '<': 'asc'}
        if 'sort' in kwargs and isinstance(kwargs['sort'], list):
            sorts = []
            for a in kwargs['sort']:
                if a[0] not in directions:
                    a = '>' + a
                sorts.append({
                    'field': a[1:],
                    'direction': directions[a[0]]
                })
            del kwargs['sort']
            kwargs['sort'] = sorts
        return Search(**kwargs)

    def found(self):
        """ Small query to determine total number of hits """
        if 'ids' in self.kwargs:
            return len(self.kwargs['ids'])
        kwargs = {
            'page': 1,
            'limit': 0
        }
        kwargs.update(self.kwargs)
        results = self.query(**kwargs)
        return results['meta']['found']

    @classmethod
    def query(cls, url=op.join(config.API_URL, 'stac/search'), **kwargs):
        """ Get request """
        logger.debug('Query URL: %s, Body: %s' % (url, json.dumps(kwargs)))
        response = requests.post(url, data=json.dumps(kwargs))
        # API error
        if response.status_code != 200:
            raise SatSearchError(response.text)
        return response.json()

    @classmethod
    def collection(cls, cid):
        """ Get a Collection record """
        url = op.join(config.API_URL, 'collections', cid)
        return Collection(cls.query(url=url))

    @classmethod
    def items_by_id(cls, ids, collection):
        """ Return Items from collection with matching ids """
        col = cls.collection(collection)
        items = []
        base_url = op.join(config.API_URL, 'collections', collection, 'items')
        for id in ids:
            items.append(Item(cls.query(op.join(base_url, id))))
        return Items(items, collections=[col])

    def items(self, limit=1000):
        """ Return all of the Items and Collections for this search """
        _limit = 1000
        if 'ids' in self.kwargs:
            col = self.kwargs.get('query', {}).get('collection', {}).get('eq', None)
            if col is None:
                raise SatSearchError('Collection required when searching by id')
            return self.items_by_id(self.kwargs['ids'], col)

        items = []
        found = self.found()
        maxitems = min(found, limit)
        kwargs = {
            'page': 1,
            'limit': min(_limit, maxitems)
        }
        kwargs.update(self.kwargs)
        while len(items) < maxitems:
            items += [Item(i) for i in self.query(**kwargs)['features']]
            kwargs['page'] += 1

        # retrieve collections
        collections = []
        for c in set([item.properties['collection'] for item in items if 'collection' in item.properties]):
            collections.append(self.collection(c))
            #del collections[c]['links']

        # merge collections into items
        #_items = []
        #for item in items:
        #    import pdb; pdb.set_trace()
        #    if 'collection' in item['properties']:
        #        item = dict_merge(item, collections[item['properties']['collection']])
        #    _items.append(Item(item))

        return Items(items, collections=collections, search=self.kwargs)
