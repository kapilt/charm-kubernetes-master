#!/usr/bin/python
"""

"""
import os
import sys

from charmhelpers.core import hookenv, host

hooks = hookenv.Hooks()


@hooks.hook('config-changed')
def config_changed():
    print "config-changed"
    relation_changed()


@hooks.hook('etcd-relation-changed', 'minions-api-relation-changed')
def relation_changed():
    template_data = get_template_data()

    # Check required keys
    missing = False
    for k in ('etcd_servers', 'minions'):
        if not template_data.get(k):
            print "missing data for", k
            missing = True
    if missing:
        print "have data\n", template_data
        return
    else:
        print "running with\n", template_data

    # Render and restart as needed
    for n in ('apiserver', 'controller-manager', 'scheduler'):
        render_file(n, template_data)
        host.service_restart(n)

    if render_file('nginx', template_data,
                   'conf.tmpl', '/etc/nginx/sites-enabled/default'):
        host.service_reload('nginx')

    # Send api endpoint to minions
    rel = hookenv.relation_id()
    print "relation id", rel
    if rel and rel.startswith("minions-api:"):
        hookenv.relation_set(
            hostname=hookenv.unit_private_ip(), port=8080)


def get_template_data():
    rels = hookenv.relations()
    template_data = {}
    template_data['etcd_servers'] = ",".join([
        "http://%s:%s" % (s[0], s[1]) for s in sorted(
            get_rel_hosts('etcd', rels, ('hostname', 'port')))])
    template_data['minions'] = ",".join(get_rel_hosts('minions-api', rels))
    template_data['api_bind_address'] = hookenv.unit_private_ip()
    template_data['bind_address'] = "127.0.0.1"
    template_data['api_server_address'] = "http://%s:%s" % (
        hookenv.unit_private_ip(), 8080)
    _encode(template_data)
    return template_data


def _encode(d):
    for k, v in d.items():
        if isinstance(v, unicode):
            d[k] = v.encode('utf8')


def get_rel_hosts(rel_name, rels, keys=('private-address',)):
    hosts = []
    for r, data in rels.get(rel_name, {}).items():
        for unit_id, unit_data in data.items():
            if unit_id == hookenv.local_unit():
                continue
            values = [unit_data.get(k) for k in keys]
            if not all(values):
                continue
            hosts.append(len(values) == 1 and values[0] or values)
    return hosts


def render_file(name, data, src_suffix="upstart.tmpl", tgt_path=None):
    tmpl_path = os.path.join(
        os.environ.get('CHARM_DIR'), 'files', '%s.%s' % (name, src_suffix))

    with open(tmpl_path) as fh:
        tmpl = fh.read()
    rendered = tmpl % data

    if tgt_path is None:
        tgt_path = '/etc/init/%s.conf' % name

    if os.path.exists(tgt_path):
        with open(tgt_path) as fh:
            contents = fh.read()
        if contents == rendered:
            return False

    with open(tgt_path, 'w') as fh:
        fh.write(rendered)
    return True

if __name__ == '__main__':
    hooks.execute(sys.argv)
