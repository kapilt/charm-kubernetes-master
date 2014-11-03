#!/usr/bin/python
"""

"""
import os
import socket
import sys

from charmhelpers.core import hookenv, host

hooks = hookenv.Hooks()


@hooks.hook('config-changed')
def config_changed():
    """
    Called whenever our service configuration changes.
    """
    relation_changed()


@hooks.hook('etcd-relation-changed', 'minions-api-relation-changed')
def relation_changed():
    template_data = get_template_data()

    # Check required keys
    for k in ('etcd_servers',):
        if not template_data.get(k):
            print "Missing data for", k, template_data
            return

    print "Running with\n", template_data

    # Render and restart as needed
    for n in ('apiserver', 'controller-manager', 'scheduler'):
        if render_file(n, template_data) or not host.service_running(n):
            host.service_restart(n)

    if render_file(
            'nginx', template_data,
            'conf.tmpl', '/etc/nginx/sites-enabled/default') or \
            not host.service_running('nginx'):
        host.service_reload('nginx')

    # Send api endpoint to minions
    notify_minions()


def notify_minions():
    print("Notify minions.")
    for r in hookenv.relation_ids('minions-api'):
        hookenv.relation_set(
            r,
            hostname=hookenv.unit_private_ip(),
            port=8080)


def get_template_data():
    rels = hookenv.relations()
    template_data = {}
    template_data['etcd_servers'] = ",".join([
        "http://%s:%s" % (s[0], s[1]) for s in sorted(
            get_rel_hosts('etcd', rels, ('hostname', 'port')))])
    template_data['minions'] = ",".join(get_rel_hosts('minions-api', rels))

    template_data['api_bind_address'] = _bind_addr(hookenv.unit_private_ip)
    template_data['bind_address'] = "127.0.0.1"
    template_data['api_server_address'] = "http://%s:%s" % (
        hookenv.unit_private_ip(), 8080)
    _encode(template_data)
    return template_data


def _bind_addr(addr):
    if addr.replace('.', '').isdigit():
        return addr
    try:
        return socket.gethostbyname(addr)
    except socket.error:
            raise ValueError("Could not resolve private address")


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
