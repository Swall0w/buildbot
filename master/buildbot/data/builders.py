# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

from twisted.internet import defer
from buildbot.data import base

class BuilderEndpoint(base.Endpoint):

    pathPatterns = [ ( 'builder', 'i:builderid' ),
                     ( 'master', 'i:masterid', 'builder', 'i:builderid' ) ]

    @defer.inlineCallbacks
    def get(self, options, kwargs):
        builderid = kwargs['builderid']
        bdict = yield self.master.db.builders.getBuilder(builderid)
        if not bdict:
            yield defer.returnValue(None)
            return
        if 'masterid' in kwargs:
            if kwargs['masterid'] not in bdict['masterids']:
                yield defer.returnValue(None)
                return
        yield defer.returnValue(
            dict(builderid=builderid,
                 name=bdict['name'],
                 link=base.Link(('builder', str(kwargs['builderid'])))))


class BuildersEndpoint(base.Endpoint):

    rootLinkName = 'builders'
    pathPatterns = [ ( 'builder', ),
                     ( 'master', 'i:masterid', 'builder' ) ]

    @defer.inlineCallbacks
    def get(self, options, kwargs):
        bdicts = yield self.master.db.builders.getBuilders(
                masterid=kwargs.get('masterid', None))
        yield defer.returnValue([
            dict(builderid=bd['id'],
                 name=bd['name'],
                 link=base.Link(('builder', str(bd['id']))))
            for bd in bdicts ])

    def startConsuming(self, callback, options, kwargs):
        return self.master.mq.startConsuming(callback,
                ('builder', None, 'new'))


class BuildersResourceType(base.ResourceType):

    type = "builder"
    endpoints = [
        BuilderEndpoint, BuildersEndpoint,
    ]
    keyFields = [ 'builderid' ]

    def __init__(self, master):
        base.ResourceType.__init__(self, master)

    @base.updateMethod
    @defer.inlineCallbacks
    def updateBuilderList(self, masterid, builderNames):
        # get the "current" list of builders for this master, so we know what
        # changes to make.  Race conditions here aren't a great worry, as this
        # is the only master inserting or deleting these records.
        builders = yield self.master.db.builders.getBuilders(masterid=masterid)

        # figure out what to remove and remove it
        builderNames_set = set(builderNames)
        for bldr in builders:
            if bldr['name'] not in builderNames_set:
                yield self.master.db.builders.removeBuilderMaster(
                        masterid=masterid, builderid=bldr['id'])
            else:
                builderNames_set.remove(bldr['name'])

        # now whatever's left in builderNames_set is new
        for name in builderNames_set:
            builderid = yield self.master.db.builders.findBuilderId(name)
            yield self.master.db.builders.addBuilderMaster(
                        masterid=masterid, builderid=builderid)
