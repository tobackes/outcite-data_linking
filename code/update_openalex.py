#-IMPORTS-----------------------------------------------------------------------------------------------------------------------------------------
import sys, os
import time
import json
from copy import deepcopy as copy
from elasticsearch import Elasticsearch as ES
from elasticsearch.helpers import streaming_bulk as bulk
from common import *
from pathlib import Path
#-------------------------------------------------------------------------------------------------------------------------------------------------
#-GLOBAL OBJECTS----------------------------------------------------------------------------------------------------------------------------------
_index = sys.argv[1]; #'geocite' #'ssoar'

IN = None;
try:
    IN = open(str((Path(__file__).parent / '../code/').resolve())+'/configs_custom.json');
except:
    IN = open(str((Path(__file__).parent / '../code/').resolve())+'/configs.json');
_configs = json.load(IN);
IN.close();

_buffer = _configs['buffer_openalex'];

_chunk_size      = _configs['chunk_size_openalex'];
_request_timeout = _configs['requestimeout_openalex'];

_recheck = _configs['recheck_openalex'];
_retest  = _configs['retest_openalex']; # Recomputes the URL even if there is already one in the index, but this should be conditioned on _recheck anyways, so only for docs where has_.._url=False
_resolve = _configs['resolve_openalex']; # Replaces the URL with the redirected URL if there should be redirection

#====================================================================================
_index_m    = 'openalex'; # Not actually required for crossref as the id is already the doi
_from_field = 'openalex_id';
_to_field   = 'openalex_urls';
#====================================================================================
#-------------------------------------------------------------------------------------------------------------------------------------------------
#-FUNCTIONS---------------------------------------------------------------------------------------------------------------------------------------

def get_url(refobjects,field,id_field,cur=None,USE_BUFFER=None):
    ids = [];
    for i in range(len(refobjects)):
        #print(refobjects[i]);
        url = None;
        ID  = None;
        if id_field in refobjects[i] and (_retest or not (_to_field[:-1] in refobjects[i] and refobjects[i][_to_field[:-1]])):
            opa_id = refobjects[i][id_field];
            page   = _client_m.search(index=_index_m, body={"query":{"term":{"id.keyword":opa_id}}} );
            doi    = doi2url(page['hits']['hits'][0]['_source']['doi'],cur,USE_BUFFER) if len(page['hits']['hits'])>0 and 'doi' in page['hits']['hits'][0]['_source'] and page['hits']['hits'][0]['_source']['doi'] else None;
            link   = page['hits']['hits'][0]['_source']['url'] if len(page['hits']['hits'])>0 and 'url' in page['hits']['hits'][0]['_source'] else None;
            url    = doi if doi else link if link else opa_id if opa_id else None;
            print(url);
        else:
            #print(id_field,'not in reference.');
            continue;
        ID = check(url,_resolve,cur,5);
        if ID != None:
            refobjects[i][field[:-1]] = ID;
            ids.append(ID);
            #print(refobjects[i]);
    return set(ids), refobjects;

#-------------------------------------------------------------------------------------------------------------------------------------------------
#-SCRIPT------------------------------------------------------------------------------------------------------------------------------------------

_client   = ES(['http://localhost:9200'],timeout=60);#ES(['localhost'],scheme='http',port=9200,timeout=60);
_client_m = ES(['http://localhost:9200'],timeout=60);#ES(['localhost'],scheme='http',port=9200,timeout=60);

i = 0;
for success, info in bulk(_client,search(_to_field,_from_field,_index,_recheck,get_url,_buffer),chunk_size=_chunk_size, request_timeout=_request_timeout):
    i += 1;
    if not success:
        print('\n[!]-----> A document failed:', info['index']['_id'], info['index']['error'],'\n');
    print(i,info)
    if i % _chunk_size == 0:
        print(i,'refreshing...');
        _client.indices.refresh(index=_index);
print(i,'refreshing...');
_client.indices.refresh(index=_index);
#-------------------------------------------------------------------------------------------------------------------------------------------------
