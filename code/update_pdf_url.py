#-IMPORTS-----------------------------------------------------------------------------------------------------------------------------------------
import sys, os
import time
import json
from copy import deepcopy as copy
from elasticsearch import Elasticsearch as ES
from elasticsearch.helpers import streaming_bulk as bulk
from common import *
from pathlib import Path
import sqlite3
import re
#-------------------------------------------------------------------------------------------------------------------------------------------------
#-GLOBAL OBJECTS----------------------------------------------------------------------------------------------------------------------------------
_index  = sys.argv[1]; #'geocite' #'ssoar'
_dbfile = sys.argv[2];#'resources/doi2pdfs.db';
_target = sys.argv[3] if len(sys.argv)>3 else None;

IN = None;
try:
    IN = open(str((Path(__file__).parent / '../code/').resolve())+'/configs_custom.json');
except:
    IN = open(str((Path(__file__).parent / '../code/').resolve())+'/configs.json');
_configs = json.load(IN);
IN.close();

_buffer = _configs['buffer_pdf'];

_chunk_size      = _configs['chunk_size_pdf'];
_request_timeout = _configs['requestimeout_pdf'];

_recheck = _configs['recheck_pdf'];
_retest  = _configs['retest_pdf']; # Recomputes the URL even if there is already one in the index, but this should be conditioned on _recheck anyways, so only for docs where has_.._url=False
_resolve = _configs['resolve_pdf']; # Replaces the URL with the redirected URL if there should be redirection

_refobjs = _configs['refobjs'];

_con = sqlite3.connect(_dbfile);
_cur = _con.cursor();

ARXIVURL = re.compile("((https?:\/\/www\.)|(https?:\/\/)|(www\.))arxiv\.org\/(abs|pdf)\/[0-9]+\.[0-9]+(\.pdf)?");
ARXIVID = re.compile("[0-9]+\.[0-9]+");

#====================================================================================
_from_field = _target+'_id' if _target=='ssoar' or _target=='arxiv' else _target+'_doi' if _target else 'doi';
_to_field   = 'fulltext_urls'; # WARNING: The difference to the usual procedure is that this is used multiple times for different _target, which means processed_fulltext_url=true
#====================================================================================
#-------------------------------------------------------------------------------------------------------------------------------------------------
#-FUNCTIONS---------------------------------------------------------------------------------------------------------------------------------------

def get_url(refobjects,field,id_field,cur=None): # This actually gets the doi not the url
    ids = [];
    for i in range(len(refobjects)):
        urls_etc = [];
        urls_pdf = [];
        ID   = None;
        if id_field=='ssoar_id' and 'ssoar_id' in refobjects[i] and refobjects[i]['ssoar_id'] and (_retest or not (_to_field[:-1] in refobjects[i] and refobjects[i][_to_field[:-1]])):
            handle = refobjects[i]['ssoar_id'].split('-')[-1];
            url    = 'https://www.ssoar.info/ssoar/bitstream/handle/document/'+handle+'/?sequence=1';
            url    = check(url,False,cur,5);
            if url:
                urls_pdf.append(url);
        elif id_field=='arxiv_id' and 'arxiv_id' in refobjects[i] and refobjects[i]['arxiv_id'] and (_retest or not (_to_field[:-1] in refobjects[i] and refobjects[i][_to_field[:-1]])):
            url = 'https://arxiv.org/pdf/'+refobjects[i]['arxiv_id']+'.pdf';
            urls_pdf.append(url);
        elif id_field in refobjects[i] and refobjects[i][id_field] and (_retest or not (_to_field[:-1] in refobjects[i] and refobjects[i][_to_field[:-1]])):
            doi   = refobjects[i][id_field].lower().rstrip('.'); print('--->',doi);
            arxiv = extract_arxiv_id(doi);
            url_  = doi2url(doi,cur) if not (doi.startswith('arxiv:') or (doi.startswith('abs/') and ARXIVID.search(doi))) else 'https://arxiv.org/pdf/'+arxiv+'.pdf' if arxiv else None;
            alt   = [url_] if url_ and url_.endswith('.pdf') else [];
            urls_ = [row[0] for row in _cur.execute("SELECT pdf_url FROM doi2pdfs WHERE doi=? ORDER BY id DESC",(doi,)).fetchall()]+alt;
            for url in urls_:
                if url and not ARXIVURL.match(url):
                    url = check(url,_resolve,cur,5) if url else None;
                else:
                    print(url);
                if url:
                    if url.endswith('.pdf'):
                        urls_pdf.append(url);
                    else:
                        urls_etc.append(url);
        else:
            continue;
        urls = urls_pdf + urls_etc;
        for url in urls:
            ID = url;#check(url,_resolve,5) if url else None;
            if ID != None:
                refobjects[i][field[:-1]] = ID;
                ids.append(ID);
            break;
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

_con.close();
#-------------------------------------------------------------------------------------------------------------------------------------------------