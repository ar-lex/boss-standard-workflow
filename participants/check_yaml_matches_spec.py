#!/usr/bin/python --tt
"""Check the yaml and spec file coherence in submit request.

The check does the following for each package:

  #. If spec file is present and claims to be generated by spectacle, make sure
     that also yaml file is present.
  #. If yaml file is present, make sure that executing specify does not change
     the spec file

:term:`Workitem` fields IN:

:Parameters:
    :ev.actions:
        List of OBS submit request actions describing the projects,
        packages, and revisions to look into.
    :ev.namespace:
        OBS alias definig the API URL to use


:term:`Workitem` fields OUT:

:Returns:
    result(Boolean):
        False if check failed

Check respects the values in [checks] section of packages boss.conf
for following keys:

    check_yaml_matches_spec:
        skip/warn this check

"""

import re, subprocess
from buildservice import BuildService
from boss.checks import CheckActionProcessor
from boss.lab import Lab

DEFAULT_SPEC_PATTERN = "Generated by: spectacle"


class ParticipantHandler(object):
    """Participant class as defined by the SkyNET API."""

    def __init__(self):
        self.oscrc = None
        self.namespace = None
        self.obs = None
        self.spec_re = None

    def handle_lifecycle_control(self, ctrl):
        """Participant life cycle control."""
        if ctrl.message == "start":
            if ctrl.config.has_option("obs", "oscrc"):
                self.oscrc = ctrl.config.get("obs", "oscrc")
            else:
                raise RuntimeError("Participant config missing "
                        "[obs] oscrc option")
            if ctrl.config.has_option("check_yaml", "spec_pattern"):
                pat = ctrl.config.get("check_yaml", "spec_pattern")
            else:
                pat = DEFAULT_SPEC_PATTERN
            self.spec_re = re.compile(pat)
            print "oscrc: %s" % self.oscrc
            print "spec_pattern: %s" % pat

    def handle_wi_control(self, ctrl):
        """Job control."""
        pass

    def setup_obs(self, namespace):
        """Set up OBS instance."""
        if not self.obs or self.namespace != namespace:
            self.obs = BuildService(oscrc=self.oscrc, apiurl=namespace)
            self.namespace = namespace

    def handle_wi(self, wid):
        """Job thread."""
        wid.result = False
        if not isinstance(wid.fields.msg, list):
            wid.fields.msg = []

        if not wid.fields.ev:
            raise RuntimeError("Missing mandatory field 'ev'")
        if not isinstance(wid.fields.ev.actions, list):
            raise RuntimeError("Mandatory field ev.actions not a list")
        if not isinstance(wid.fields.ev.namespace, basestring):
            raise RuntimeError("Mandatory field ev.namespace not a string")

        self.setup_obs(wid.fields.ev.namespace)

        result = True
        for action in wid.fields.ev.actions:
            pkg_result, _ = self.__handle_action(action, wid)
            result = result and pkg_result
        wid.result = result

    @CheckActionProcessor("check_yaml_matches_spec")
    def __handle_action(self, action, _wid):
        """Process single action from OBS event info.

        :param action: Single dictionary from OBS event actions list
        :returns: True if all good, False otherwise
        """
        project = action["sourceproject"]
        package = action["sourcepackage"]
        revision = action["sourcerevision"]
        files = self.obs.getPackageFileList(project, package, revision)

        with Lab(prefix="check_yaml_spec_") as lab:
            spec = None
            yaml = None
            for name in files:
                if name.endswith(".spec"):
                    lab.store(name, self.obs.getFile(project, package, name,
                        revision))
                    spec = name
                elif name.endswith(".yaml"):
                    lab.store(name, self.obs.getFile(project, package, name,
                        revision))
                    yaml = name

            if not (spec and self.spec_re.search(lab.open(spec).read())):
                # No spec file or spec not from spectacle, skip
                return True, None
            if not yaml:
                return False, "SPEC file generated with spectacle, " \
                              "but yaml not present"

            snapshot = lab.take_snapshot()
            # Download rest of the files
            files.remove(spec)
            files.remove(yaml)
            for name in files:
                lab.store(name, self.obs.getFile(project, package, name,
                        revision))

            # Run specify
            specify = subprocess.Popen(["specify", "-n", "-N",
                lab.real_path(yaml)], stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, env={"ANSI_COLORS_DISABLED":"1"})
            rcode = specify.wait()
            if rcode != 0:
                return False, "Running specify failed:\n%s" \
                        % specify.stdout.read()
            # Get the diff
            diff = lab.get_diff(spec, snapshot)
            clean_diff = []
            for line in diff:
                # ignore the ? seperator lines
                if line[0] == "?":
                    continue
                # Remove diff markers and white space
                stripped = line[2:].strip()
                # skip empty lines
                if not stripped:
                    continue
                # skip comments
                if stripped[0] == "#":
                    continue
                # effective change
                clean_diff.append(line)
            if clean_diff:
                return False, "Spec file changed by specify:\n%s" \
                        % "".join(clean_diff)
        return True, None

