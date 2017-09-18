# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2017 Lenovo
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# this will implement noderange grammar


import codecs
import struct
import eventlet.green.socket as socket
import eventlet.support.greendns
getaddrinfo = eventlet.support.greendns.getaddrinfo


def ip_on_same_subnet(first, second, prefix):
    addrinf = socket.getaddrinfo(first, None, 0, socket.SOCK_STREAM)[0]
    fam = addrinf[0]
    ip = socket.inet_pton(fam, addrinf[-1][0])
    ip = int(codecs.encode(bytes(ip), 'hex'), 16)
    addrinf = socket.getaddrinfo(second, None, 0, socket.SOCK_STREAM)[0]
    if fam != addrinf[0]:
        return False
    oip = socket.inet_pton(fam, addrinf[-1][0])
    oip = int(codecs.encode(bytes(oip), 'hex'), 16)
    if fam == socket.AF_INET:
        addrlen = 32
    elif fam == socket.AF_INET6:
        addrlen = 128
    else:
        raise Exception("Unknown address family {0}".format(fam))
    mask = 2 ** prefix - 1 << (addrlen - prefix)
    return ip & mask == oip & mask


# TODO(jjohnson2): have a method to arbitrate setting methods, to aid
# in correct matching of net.* based on parameters, mainly for pxe
# The scheme for pxe:
# For one: the candidate net.* should have pxe set to true, to help
# disambiguate from interfaces meant for bmc access
# bmc relies upon hardwaremanagement.manager, plus we don't collect
# that mac address
# the ip as reported by recvmsg to match the subnet of that net.* interface
# if switch and port available, that should match.
def get_nic_config(configmanager, node, ip=None, mac=None):
    """Fetch network configuration parameters for a nic
    
    For a given node and interface, find and retrieve the pertinent network
    configuration data.  The desired configuration can be searched
    either by ip or by mac.
    
    :param configmanager: The relevant confluent.config.ConfigManager 
        instance.
    :param node:  The name of the node
    :param ip:  An IP address on the intended subnet
    :param mac: The mac address of the interface
    
    :returns: A dict of parameters, 'ipv4_gateway', ....
    """
    # ip parameter *could* be the result of recvmsg with cmsg to tell
    # pxe *our* ip address, or it could be the desired ip address
    #TODO(jjohnson2): ip address, prefix length, mac address,
    # join a bond/bridge, vlan configs, etc.
    # also other nic criteria, physical location, driver and index...
    nodenetattribs = configmanager.get_node_attributes(
        node, 'net*.ipv4_gateway').get(node, {})
    cfgdata = {
        'ipv4_gateway': None,
        'prefix': None,
    }
    if ip is not None:
        prefixlen = get_prefix_len_for_ip(ip)
        cfgdata['prefix'] = prefixlen
        for setting in nodenetattribs:
            gw = nodenetattribs[setting].get('value', None)
            if gw is None:
                continue
            if ip_on_same_subnet(ip, gw, prefixlen):
                cfgdata['ipv4_gateway'] = gw
                break
    return cfgdata


def get_prefix_len_for_ip(ip):
    # for now, we'll use the system route table
    # later may provide for configuration lookup to override the route
    # table
    ip = getaddrinfo(ip, 0, socket.AF_INET)[0][-1][0]
    try:
        ipn = socket.inet_aton(ip)
    except socket.error:  # For now, assume 64 for ipv6
        return 64
    # It comes out big endian, regardless of host arch
    ipn = struct.unpack('>I', ipn)[0]
    rf = open('/proc/net/route')
    ri = rf.read()
    rf.close()
    ri = ri.split('\n')[1:]
    for rl in ri:
        if not rl:
            continue
        rd = rl.split('\t')
        if rd[1] == '00000000':  # default gateway, not useful for this
            continue
        # don't have big endian to look at, assume that it is host endian
        maskn = struct.unpack('I', struct.pack('>I', int(rd[7], 16)))[0]
        netn = struct.unpack('I', struct.pack('>I', int(rd[1], 16)))[0]
        if ipn & maskn == netn:
            nbits = 0
            while maskn:
                nbits += 1
                maskn = maskn << 1 & 0xffffffff
            return nbits
    raise exc.NotImplementedException("Non local addresses not supported")