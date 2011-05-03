#!/usr/bin/python
""" Quality check participant """

from buildservice import BuildService

class ParticipantHandler(object):

    """ Participant class as defined by the SkyNET API """

    def __init__(self):
        self.obs = None
        self.oscrc = None

    def handle_wi_control(self, ctrl):
        """ job control thread """
        pass
    
    def handle_lifecycle_control(self, ctrl):
        """ participant control thread """
        if ctrl.message == "start":
            if ctrl.config.has_option("obs", "oscrc"):
                self.oscrc = ctrl.config.get("obs", "oscrc")
    
    def setup_obs(self, namespace):
        """ setup the Buildservice instance using the namespace as an alias
            to the apiurl """

        self.obs = BuildService(oscrc=self.oscrc, apiurl=namespace)

    def is_complete(self, prj, pkg, revision):

        """ Package file completeness check """

        filelist = self.obs.getPackageFileList(prj, pkg, revision)
        specfile = changesfile = sourcefile = False
        for fil in filelist:
            sourcefile = True if fil.endswith(".tar.bz2") \
                              or fil.endswith(".tar.gz")  \
                              or fil.endswith(".tgz")     \
                              or sourcefile                \
                              else False
            changesfile = True if fil.endswith(".changes") \
                          or changesfile                    \
                          else False
            specfile = True if fil.endswith(".spec") \
                            or specfile               \
                            else False
        return sourcefile and changesfile and specfile

    def quality_check(self, wid):

        """ Quality check implementation """

        wid.result = False
        msg = wid.fields.msg if wid.fields.msg else []
        actions = wid.fields.ev.actions

        if not actions:
            wid.set_field("__error__", "A needed field does not exist.")
            return

        result = True

        for action in actions:
            # Assert needed files are there.
            if not self.is_complete(action['sourceproject'],
                                    action['sourcepackage'],
                                    action['sourcerevision']):
                result = False
                msg.append("Package %s in project %s missing files. At least \
                            compressed source tarball, .spec and .changes \
                            files should be present" % (action['sourcepackage'],
                                                       action['sourceproject']))

        wid.set_field("msg", msg)
        wid.result = result

    def handle_wi(self, wid):

        """ actual job thread """

        # We may want to examine the fields structure
        if wid.fields.debug_dump or wid.params.debug_dump:
            print wid.dump()

        self.setup_obs(wid.namespace)
        self.quality_check(wid)
