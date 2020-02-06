import uuid, logging
import math
import ndex2
import pandas
from app.api.bigquery.business_interactions import get_request_status

glogger = logging.getLogger()

def ndex(request):
    if 'request_id' not in request:
        return {'status':'error',
                'message':'request_id is required'}
    else:
        request_id = request['request_id']
    if 'username' not in request or len(request['username'].strip()) == 0:
        username = 'biggim'
    else:
        username = request['username']
    if 'password' not in request or len(request['password'].strip()) == 0:
        password = 'ncats'
    else:
        password = request['password']
    if 'network_name' not in request or len(request['network_name'].strip()) == 0:
        network_name = None
    else:
        network_name = request['network_name']
    if 'network_set' not in request or len(request['network_set'].strip()) == 0:
        network_set = None
    else:
        network_set = request['network_set']
    response = push_to_ndex(request_id, username=username, password=password,
                 network_name = network_name,
                 network_set_name=network_name,
                 network_set_description=None)
    return response


def push_to_ndex(biggim_id, username='biggim', password='ncats', server="http://public.ndexbio.org",
                 network_name = None,
                 network_set_name=None, network_set_description=None):
    glogger.debug("Looking for biggim request [%s]" % (biggim_id))
    request_status = get_request_status(biggim_id)
    while request_status['status'] == 'running':
        time.sleep(1)
        request_status = get_request_status(biggim_id)
    glogger.debug("Request search response[%s]" % (str(request_status)))
    if request_status['status'] == 'complete':
        csvs = request_status['request_uri']
    else:
        glogger.error("Error attempting to get [%s]" % (biggim_id))
        return request_status
    if network_set_name is None:
        network_set_name = "Anonymous"
        network_set_description = "Biggim network"
    if network_name is None:
        network_name = "Biggim - [%s]" % (biggim_id,)
    try:
        my_ndex=ndex2.Ndex2(server, username, password)
        my_ndex.update_status()
    except Exception as inst:
        glogger.exception("Could not access account %s with password %s" % (username, password))
        return {'status':'error', 'message':"Invalid authentication to NDEX"}
    user = my_ndex.get_user_by_username(username)
    if network_set_name is None:
        network_set = "Anonymous"
        network_set_description = "Autogenerated biggim ndex file.  CSV source at %s" % csv_url
    ctr = 0
    ndex_urls = []
    ndex_ids = []
    public_url = []
    for csv_url in csvs:
        df = pandas.read_csv(csv_url)

        df.loc[:, 'Interaction'] = 'coexpression'

        non_att = ['GPID', 'Gene1', 'Gene2', 'Interaction']
        edge_attr =[c for c in df.columns if c not in non_att]
        df.loc[:, 'Gene1'] = df.apply(lambda x: "ncbigene:%i" % x['Gene1'], axis=1)
        df.loc[:, 'Gene2'] = df.apply(lambda x: "ncbigene:%i" % x['Gene2'], axis=1)
        niceCx_df_with_headers = ndex2.create_nice_cx_from_pandas(df, source_field='Gene1', target_field='Gene2',
                                  edge_attr=edge_attr, edge_interaction='Interaction')
        # add gene context for lookup
        context = [{'ncbigene': 'http://identifiers.org/ncbigene/'}]
        niceCx_df_with_headers.set_name("%s - [%i]" % (network_name, ctr))
        ndex_network_url = niceCx_df_with_headers.upload_to(server, username, password, visibility='PUBLIC')

        ndex_urls.append(ndex_network_url)
        ndex_network_uuid = ndex_network_url.split('/')[-1]
        ndex_ids.append(ndex_network_uuid)
        public_url.append("http://www.ndexbio.org/#/network/%s" % (ndex_network_uuid,))
        ctr += 1
    net_set_uuid = None
    network_sets = my_ndex.get('/user/%s/networksets' % user['externalId'])
    for ns in network_sets:
        if ns['name'] == network_set_name:
            net_set_uuid = ns['externalId']
    if net_set_uuid is None:
        net_set_url = my_ndex.create_networkset(network_set_name, network_set_description)
        net_set_uuid = net_set_url.split('/')[-1]
    my_ndex.add_networks_to_networkset(net_set_uuid, [ndex_network_uuid])
    return {'status':'complete', 'request_id':biggim_id, 'ndex_network_url':ndex_urls,
            'ndex_network_uuid':ndex_ids, 'ndex_public_url': public_url
    }
