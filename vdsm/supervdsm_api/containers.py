# Copyright 2016 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
from __future__ import absolute_import

from vdsm import commands
from vdsm import utils

from . import expose


_DOCKER = utils.CommandPath("docker",
                            "/bin/docker",
                            "/usr/bin/docker",
                            )


@expose
def docker_net_inspect(network):
    return commands.execCmd([
        _DOCKER.cmd,
        'network',
        'inspect',
        network,
    ])


@expose
def docker_net_create(subnet, gw, nic, network):
    return commands.execCmd([
        _DOCKER.cmd,
        'network',
        'create',
        '-d macvlan',
        '--subnet=%s' % subnet,
        '--gateway=%s' % gw,
        '--ip-range=%s' % subnet,
        '-o parent=%s' % nic,
        network,
    ])


@expose
def docker_net_remove(network):
    return commands.execCmd([
        _DOCKER.cmd,
        'network',
        'rm',
        network,
    ])
