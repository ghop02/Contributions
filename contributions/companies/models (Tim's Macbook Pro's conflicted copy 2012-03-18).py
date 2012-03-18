from django.db import models
from transparencydata import TransparencyData
from django.conf import settings
import httplib, urllib
import json

td = TransparencyData(settings.TRANSPARENCY_DATA_API)

# the following is a copy of Chrome's headers; Maplight seems to accept
# Chrome but not Python.
MAPLIGHT_HEADERS = {
  'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Charset':'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
  'Accept-Encoding':'gzip,deflate,sdch',
  'Accept-Language':'en-US,en;q=0.8',
  #'Cache-Control':'max-age=0',
  #'Connection':'keep-alive',
  'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_3) AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.79 Safari/535.11'
}

def maplight_search(command, args):
  """
  >>> maplight_search('organization_search', {'search' : 'microsoft'})
  """
  args['apikey'] = settings.MAPLIGHT_API
  conn = httplib.HTTPConnection("maplight.org")
  conn.set_debuglevel(3)
  print "/services_open_api/map.%s_v1.json" % command
  print urllib.urlencode(args)
  conn.request("GET", "/services_open_api/map.%s_v1.json" % command, urllib.urlencode(args), MAPLIGHT_HEADERS)
  return json.load(conn.getresponse())

class CompanyManager(models.Manager):
  def create_from_search(self, query):
    maplight_search('organization_search', {'@search' : query})

  def search(self, query): # may be replaced later
    if query == '':
      return all()
    c = self
    for i in query.split():
      c = c.filter(name__contains = query)
    if len(c) == 0:
      return [] # search TD and Maplight
    else:
      return c

class Contribution(object):
  pass

class Position(object):
  pass

class Company(models.Model):
  name = models.CharField(max_length=255)
  industry = models.CharField(max_length=255)
  parent = models.ForeignKey('self')
  date_created = models.DateTimeField()
  date_modified = models.DateTimeField()
  maplight_id = models.CharField(max_length=255)
  
  objects = CompanyManager()
  
  def position_set(self):
    return maplight_search('organization_positions',
      {'@organization_id' : self.maplight_id, '@jurisdiction' : 'us'})
  
  def contribution_set(self, **kwargs):
    cont = td.contributions(organization_ft = self.name, **kwargs)
    return cont
    
  def save(self):
    if self.date_created == None:
      self.date_created = datetime.now()
    self.date_modified = datetime.now()
    super(Company, self).save()
    