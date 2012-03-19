from django.db import models
from transparencydata import TransparencyData
from django.conf import settings
from datetime import datetime
import httplib, urllib, json

# For all TransparencyData queries
td = TransparencyData(settings.TRANSPARENCY_DATA_API)

class CaseInsensitiveQuerySet(models.query.QuerySet):
  def _filter_or_exclude(self, mapper, *args, **kwargs):
    """
    Thanks to http://djangosnippets.org/snippets/305/
    """
    # 'name' is a field in your Model whose lookups you want case-insensitive by default
    if 'name' in kwargs:
      kwargs['name__iexact'] = kwargs['name']
      del kwargs['name']
    return super(CaseInsensitiveQuerySet, self)._filter_or_exclude(mapper, *args, **kwargs)

def maplight_search(command, args):
  """
  >>> maplight_search('organization_search', {'search' : 'microsoft'})
  {u'organizations': [{u'organization_id': u'23370', u'name': u'Microsoft'}]}
  >>> # we can't be sure of the exact results of this call, so we aren't too rigorous
  >>> d = maplight_search('organization_positions', {'organization_id' : 23370, 'jurisdiction' : 'us'})
  >>> d.__class__
  <type 'dict'>
  >>> len(d['positions']) > 0
  True
  """
  args['apikey'] = settings.MAPLIGHT_API
  encoded_args = urllib.urlencode(args)
  conn = httplib.HTTPConnection("maplight.org")
  conn.request("GET", "/services_open_api/map.%s_v1.json?%s" % (command, encoded_args))
  return json.load(conn.getresponse())

class CompanyManager(models.Manager):
  def get_query_set(self):
    return CaseInsensitiveQuerySet(self.model)

  def from_td(self, query, strict = False, name = False):
    """
    Finds companies in the database first and in the TD API second.
    
    Returns a company and its parents in a hash, with the name as a key.
    
    For a list, use .values(). For only 1 item and to use a specific name, use strict = True.
    
    Not very efficient--lots of redundant API & SQL calls
    """
    
    # should filter PAC vs company!
    contributions = td.contributions(organization_ft = query)
    seen_names = set()
    seen_names.add('')
    seen_add = seen_names.add
    td_orgs = [c for c in contributions if c['organization_name'] not in seen_names and not seen_add(c['organization_name'])]

    comp_d = {}
    
    for o in td_orgs:
      c = self.filter(name = o['organization_name'])
      if len(c) > 0:
        c = c[0]
      else:
        c = Company(name = o['organization_name'], industry = o['contributor_category'])
        c.save()
        c.parent_name = o['parent_organization_name']
      comp_d[o['organization_name']] = c
        
    first = comp_d.values()[0]
    for c in comp_d.values():
      if hasattr(c, 'parent_name'):
        if c.parent_name != u'':
          if c.parent_name not in seen_names:
            comp_d[c.parent_name] = self.from_td(c.parent_name, True)
          c.parent = comp_d[c.parent_name]
      elif strict and not c.parent:
        if c != first:
          c.parent = first
      c.save()
    
    if strict:
      return comp_d[query]
    else:
      return comp_d

  def search(self, query, strict = False): # may be replaced later
    if query == '':
      return all()
    else:
      cs = self.filter(name__contains = query)
      if len(cs) > 0:
        return cs
      else:
        return self.from_td(query, strict = strict)
    # c = self
#     for i in query.split():
#       c = c.filter(name__contains = query)
#     if len(c) == 0:
#       return self.from_td(query)
#     else:
#       return c

class Contribution(object):
  """
  A convenience class that wraps around the results TD API returns
  """
  def __init__(self, d):
    self.d = d
    self.__hash__ = d['transaction_id'].__hash__

class Position(object):
  """
  """
  def __init__(self, d):
    self.d = d
    self.__hash__ = d['url'].__hash__

class Company(models.Model):
  """
  A company with contributions and positions
  
  >>> companies = Company.objects.search('microsoft').values()
  >>> c = companies[0]
  >>> c.name
  u"Microsoft Corp"
  >>> c.parent
  >>> len(c.company_set.all())
  1
  >>> x = [c.name for c in companies]
  >>> x.sort()
  >>> x
  [u'Ignition Partners', u'MICROSOFT', u'Microsoft Canada', u'Microsoft Corp']
  >>> cont = c.contribution_set()
  >>> len(cont) > 0 # pretty mushy test
  True
  >>> c = Company.objects.search('Microsoft Canada', strict = True)
  >>> c.parent.name
  u'Microsoft Corp'
  >>> c.company_set.all()
  []
  >>> cont = c.contribution_set()
  >>> len(cont) > 0
  True
  >>> pos = c.position_set()
  >>> len(pos) == 0 # this should be > 0 - fix this
  True
  >>> companies = Company.objects.search('Nabisco Inc')
  >>> len(companies)
  13
  >>> c = companies['Nabisco Inc']
  >>> c.parent.name
  u'Kraft Foods'
  >>> len(c.position_set.all())
  2
  """
  name = models.CharField(max_length=255)
  industry = models.CharField(max_length=255, null=True)
  parent = models.ForeignKey('self', null=True)
  date_created = models.DateTimeField()
  date_modified = models.DateTimeField()
  maplight_id = models.CharField(max_length=255, null=True)
  
  objects = CompanyManager()
  
  def position_set(self, direction = 0):
    """
    Direction is positive if searching up, negative if searching down
    """
    positions = set()
    if self.maplight_id is None:
      orgs = maplight_search('organization_search', {'search' : self.name})['organizations']
      if len(orgs) > 0:
        self.maplight_id = orgs[0]['organization_id']
      else:
        self.maplight_id = ''
        self.save()
    
    if self.maplight_id != '':
      positions.update(map(Position, maplight_search('organization_positions',
      {'organization_id' : self.maplight_id, 'jurisdiction' : 'us'})['positions']))
      
    if self.parent and direction >= 0:
      positions.update(self.parent.position_set(1))
      
    if direction <= 0:
      for company in self.company_set.all():
        positions.update(company.position_set(-1))
        
    return positions
  
  def contribution_set(self, direction = 0):
    """
    Direction is positive if searching up, negative if searching down
    """
    contributions = set(map(Contribution, td.contributions(organization_ft = self.name)))
    
    if self.parent and direction >= 0:
      contributions.update(self.parent.contribution_set(1))
      
    if direction <= 0:
      for company in self.company_set.all():
        contributions.update(company.contribution_set(-1))
        
    return contributions
    
  def save(self):
    # Thanks to http://djangosnippets.org/snippets/1017/
    if self.date_created == None:
      self.date_created = datetime.now()
    self.date_modified = datetime.now()
    super(Company, self).save()
    